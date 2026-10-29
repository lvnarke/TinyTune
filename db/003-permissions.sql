ALTER TABLE app_users ADD COLUMN IF NOT EXISTS username TEXT;
ALTER TABLE app_users ADD COLUMN IF NOT EXISTS password_hash TEXT;
UPDATE app_users SET username='user_' || replace(id::text,'-','') WHERE username IS NULL;
CREATE UNIQUE INDEX IF NOT EXISTS app_users_username_idx ON app_users(lower(username));

CREATE TABLE IF NOT EXISTS playlist_members (
    playlist_id UUID NOT NULL REFERENCES playlists(id) ON DELETE CASCADE,
    user_id UUID NOT NULL REFERENCES app_users(id) ON DELETE CASCADE,
    role TEXT NOT NULL CHECK(role IN ('viewer','editor')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY(playlist_id,user_id)
);
CREATE INDEX IF NOT EXISTS playlist_members_user_idx ON playlist_members(user_id);
CREATE TABLE IF NOT EXISTS playlist_favorites (
    playlist_id UUID NOT NULL REFERENCES playlists(id) ON DELETE CASCADE,
    user_id UUID NOT NULL REFERENCES app_users(id) ON DELETE CASCADE,
    PRIMARY KEY(playlist_id,user_id)
);
INSERT INTO playlist_favorites(playlist_id,user_id)
SELECT id,owner_id FROM playlists WHERE favorite=TRUE AND owner_id IS NOT NULL
ON CONFLICT DO NOTHING;
