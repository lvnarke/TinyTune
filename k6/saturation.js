import http from 'k6/http';
import exec from 'k6/execution';
import { Counter, Rate, Trend } from 'k6/metrics';
import { sleep } from 'k6';

const BASE_URL = (__ENV.BASE_URL || 'http://localhost:8080').replace(/\/$/, '');
const RUN_LABEL = __ENV.RUN_LABEL || 'optimized';
const RATES = (__ENV.STEP_RATES || '10,25,50,100,200,400')
  .split(',')
  .map((value) => Number(value.trim()));
const STEP_SECONDS = Number(__ENV.STEP_DURATION_SECONDS || '10');
const P95_LIMIT_MS = Number(__ENV.P95_LIMIT_MS || '250');
const ERROR_LIMIT_PERCENT = Number(__ENV.ERROR_LIMIT_PERCENT || '1');
const WARMUP_RATE = Math.max(100, Math.min(1000, Math.floor(RATES[0] / 2)));

const latencyByRate = {};
const failureByRate = {};
const requestByRate = {};
const scenarios = {
  warmup: {
    executor: 'constant-arrival-rate',
    exec: 'warmup',
    rate: WARMUP_RATE,
    timeUnit: '1s',
    duration: '3s',
    preAllocatedVUs: Math.min(250, Math.max(20, Math.ceil(WARMUP_RATE / 4))),
    maxVUs: Math.max(200, WARMUP_RATE * 2),
    gracefulStop: '1s',
  },
};

RATES.forEach((rate, index) => {
  latencyByRate[rate] = new Trend(`tinytune_latency_${rate}`, true);
  failureByRate[rate] = new Rate(`tinytune_failures_${rate}`);
  requestByRate[rate] = new Counter(`tinytune_requests_${rate}`);
  scenarios[`rate_${rate}`] = {
    executor: 'constant-arrival-rate',
    exec: 'exercise',
    rate,
    timeUnit: '1s',
    duration: `${STEP_SECONDS}s`,
    startTime: `${5 + index * (STEP_SECONDS + 2)}s`,
    preAllocatedVUs: Math.min(250, Math.max(20, Math.ceil(rate / 4))),
    maxVUs: Math.max(200, rate * 2),
    gracefulStop: '0s',
    tags: { target_rps: String(rate) },
  };
});

export const options = {
  scenarios,
  summaryTrendStats: ['avg', 'min', 'med', 'max', 'p(90)', 'p(95)', 'p(99)'],
  systemTags: ['status', 'method', 'name', 'scenario'],
  noConnectionReuse: false,
  userAgent: 'TinyTune-k6-saturation/1.0',
};

function waitUntilReady() {
  for (let attempt = 0; attempt < 60; attempt += 1) {
    const response = http.get(`${BASE_URL}/health/ready`, { timeout: '2s' });
    if (response.status === 200) return;
    sleep(1);
  }
  throw new Error(`TinyTune did not become ready at ${BASE_URL}`);
}

export function setup() {
  waitUntilReady();
  const account = http.post(`${BASE_URL}/auth/signup`, JSON.stringify({
    username: `bench_${Date.now()}_${Math.floor(Math.random()*1000000)}`,
    name: 'Isolated load fixture', password: `Fixture-${Date.now()}-${Math.random()}-${Math.random()}`,
  }), {headers: {'Content-Type':'application/json', 'X-TinyTune-Request':'1'}, timeout:'10s'});
  if (account.status !== 201) throw new Error(`fixture sign-up failed: ${account.status}`);
  const cookies = http.cookieJar().cookiesForURL(BASE_URL);
  const session = cookies.tinytune_session && cookies.tinytune_session[0];
  if (!session) throw new Error('fixture session cookie missing');
  const stamp = new Date().toISOString();
  const playlistResponse = http.post(
    `${BASE_URL}/api/v1/playlists`,
    JSON.stringify({ name: `k6-${RUN_LABEL}-${stamp}` }),
    { headers: { 'Content-Type': 'application/json', 'X-TinyTune-Request':'1' }, timeout: '5s' },
  );
  if (playlistResponse.status !== 201) {
    throw new Error(`fixture playlist failed: ${playlistResponse.status} ${playlistResponse.body}`);
  }
  const playlistId = playlistResponse.json('id');
  const trackResponse = http.post(
    `${BASE_URL}/api/v1/playlists/${playlistId}/tracks`,
    JSON.stringify({ title: 'Constant Arrival Rate', artist: 'The Load Generators' }),
    { headers: { 'Content-Type': 'application/json', 'X-TinyTune-Request':'1' }, timeout: '5s' },
  );
  if (trackResponse.status !== 201) {
    throw new Error(`fixture track failed: ${trackResponse.status} ${trackResponse.body}`);
  }
  return { playlistId, trackId: trackResponse.json('id'), session };
}

export function exercise(data) {
  const rate = Number(exec.scenario.name.replace('rate_', ''));
  const sequence = exec.scenario.iterationInTest;
  let response;
  if (sequence % 10 < 7) {
    response = http.get(`${BASE_URL}/api/v1/playlists/${data.playlistId}`, {
      timeout: '8s',
      headers: {Cookie:`tinytune_session=${data.session}`},
      tags: { operation: 'playlist_read' },
    });
  } else {
    response = http.post(
      `${BASE_URL}/api/v1/playlists/${data.playlistId}/plays`,
      JSON.stringify({ track_id: data.trackId }),
      {
        headers: {
          'Content-Type': 'application/json',
          'Cookie': `tinytune_session=${data.session}`,
          'X-TinyTune-Request': '1',
          'Idempotency-Key': `${RUN_LABEL}-${rate}-${exec.vu.idInTest}-${sequence}-${Date.now()}`,
        },
        timeout: '8s',
        tags: { operation: 'play_write' },
      },
    );
  }
  const ok = response.status >= 200 && response.status < 300;
  latencyByRate[rate].add(response.timings.duration);
  failureByRate[rate].add(!ok);
  requestByRate[rate].add(1);
}

export function warmup(data) {
  http.get(`${BASE_URL}/api/v1/playlists/${data.playlistId}`, {
    timeout: '5s',
    headers: {Cookie:`tinytune_session=${data.session}`},
    tags: { operation: 'warmup' },
  });
}

function rounded(value, digits = 2) {
  if (value === undefined || value === null || Number.isNaN(value)) return null;
  return Number(value.toFixed(digits));
}

function buildReport(data) {
  const steps = RATES.map((rate) => {
    const latency = (data.metrics[`tinytune_latency_${rate}`] || { values: {} }).values;
    const failure = (data.metrics[`tinytune_failures_${rate}`] || { values: {} }).values;
    const requests = (data.metrics[`tinytune_requests_${rate}`] || { values: {} }).values;
    const count = requests.count || 0;
    const achievedRps = count / STEP_SECONDS;
    const errorPercent = (failure.rate || 0) * 100;
    const reasons = [];
    if ((latency['p(95)'] || 0) > P95_LIMIT_MS) {
      reasons.push(`p95 ${rounded(latency['p(95)'], 1)} ms > ${P95_LIMIT_MS} ms`);
    }
    if (errorPercent > ERROR_LIMIT_PERCENT) {
      reasons.push(`errors ${rounded(errorPercent, 2)}% > ${ERROR_LIMIT_PERCENT}%`);
    }
    if (achievedRps < rate * 0.90) {
      reasons.push(`achieved ${rounded(achievedRps, 1)} rps < 90% of target`);
    }
    return {
      target_rps: rate,
      requests: count,
      achieved_rps: rounded(achievedRps),
      latency_ms: {
        mean: rounded(latency.avg),
        p50: rounded(latency.med),
        p95: rounded(latency['p(95)']),
        p99: rounded(latency['p(99)']),
        max: rounded(latency.max),
      },
      error_percent: rounded(errorPercent, 3),
      saturated: reasons.length > 0,
      saturation_reasons: reasons,
    };
  });
  const saturationPoint = steps.find(
    (step, index) => step.saturated
      && (index === steps.length - 1 || steps[index + 1].saturated),
  ) || null;
  return {
    run_label: RUN_LABEL,
    generator: 'k6 constant-arrival-rate',
    generated_at: new Date().toISOString(),
    target_url: BASE_URL,
    thresholds: {
      p95_limit_ms: P95_LIMIT_MS,
      error_limit_percent: ERROR_LIMIT_PERCENT,
      minimum_achieved_ratio: 0.90,
    },
    saturation_point: saturationPoint,
    steps,
  };
}

function markdownReport(report) {
  const saturation = report.saturation_point;
  const lines = [
    `# TinyTune k6 saturation report: ${report.run_label}`,
    '',
    `Generated: ${report.generated_at}`,
    '',
    saturation
      ? `Measured saturation point: **${saturation.target_rps} target RPS** (${saturation.saturation_reasons.join('; ')}).`
      : 'No saturation threshold was crossed at the tested rates.',
    '',
    '| Target RPS | Achieved RPS | p50 ms | p95 ms | p99 ms | Errors | Saturated |',
    '|---:|---:|---:|---:|---:|---:|:---:|',
  ];
  report.steps.forEach((step) => {
    lines.push(
      `| ${step.target_rps} | ${step.achieved_rps} | ${step.latency_ms.p50} | `
      + `${step.latency_ms.p95} | ${step.latency_ms.p99} | ${step.error_percent}% | `
      + `${step.saturated ? 'yes' : 'no'} |`,
    );
  });
  lines.push('', 'Generated by k6 constant-arrival-rate scenarios.');
  return `${lines.join('\n')}\n`;
}

export function handleSummary(data) {
  const report = buildReport(data);
  const stamp = report.generated_at.replace(/[-:]/g, '').replace(/\.\d+Z$/, 'Z');
  const stem = `${stamp}-${RUN_LABEL}-k6`;
  if (__ENV.REPORT_PATH) {
    return {
      [__ENV.REPORT_PATH]: `${JSON.stringify(report, null, 2)}\n`,
      [`${__ENV.REPORT_PATH}.md`]: markdownReport(report),
    };
  }
  return {
    stdout: `${markdownReport(report)}\n`,
    [`/results/${stem}.json`]: `${JSON.stringify(report, null, 2)}\n`,
    [`/results/${stem}.md`]: markdownReport(report),
  };
}

