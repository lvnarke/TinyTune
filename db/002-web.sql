CREATE TABLE IF NOT EXISTS app_users (
    id UUID PRIMARY KEY,
    provider TEXT NOT NULL,
    provider_id TEXT NOT NULL,
    name TEXT NOT NULL,
    email TEXT,
    picture TEXT,
    library_initialized BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE(provider, provider_id)
);
ALTER TABLE playlists ADD COLUMN IF NOT EXISTS owner_id UUID REFERENCES app_users(id);
ALTER TABLE playlists ADD COLUMN IF NOT EXISTS description TEXT NOT NULL DEFAULT '';
ALTER TABLE playlists ADD COLUMN IF NOT EXISTS cover INTEGER NOT NULL DEFAULT 0;
ALTER TABLE playlists ADD COLUMN IF NOT EXISTS favorite BOOLEAN NOT NULL DEFAULT FALSE;
CREATE INDEX IF NOT EXISTS playlists_owner_idx ON playlists(owner_id);
