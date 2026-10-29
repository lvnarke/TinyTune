CREATE TABLE IF NOT EXISTS playlists (
    id UUID PRIMARY KEY,
    name TEXT NOT NULL CHECK (char_length(name) BETWEEN 1 AND 120),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS tracks (
    id UUID PRIMARY KEY,
    playlist_id UUID NOT NULL REFERENCES playlists(id) ON DELETE CASCADE,
    title TEXT NOT NULL CHECK (char_length(title) BETWEEN 1 AND 200),
    artist TEXT NOT NULL CHECK (char_length(artist) BETWEEN 1 AND 200),
    position INTEGER NOT NULL CHECK (position > 0),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (playlist_id, position)
);

CREATE INDEX IF NOT EXISTS tracks_playlist_id_idx ON tracks(playlist_id);

CREATE TABLE IF NOT EXISTS track_play_counts (
    track_id UUID PRIMARY KEY REFERENCES tracks(id) ON DELETE CASCADE,
    play_count BIGINT NOT NULL DEFAULT 0 CHECK (play_count >= 0),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS processed_events (
    event_id UUID PRIMARY KEY,
    processed_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS processed_events_processed_at_idx
    ON processed_events(processed_at);

