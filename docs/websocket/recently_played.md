# Recently played

Provides the albums, artists, playlists and tracks an account played recently, newest first, one entry each, the way the Spotify app's Recents shows them. It is built from Spotify's last 50 plays, grouped by the context they were played from.

## Request

```json
{
    "id": 1,
    "type": "spotcast/recently_played",
    "limit": 20,
    "account": "01JDG07KSBTYWZGJSBJ1EW6XEF"
}
```

### `id` (int)

*Required*

The id of the transaction. Must be an increment of the last transaction id.

### `type` (str)

*Required*

The endpoint of the WebSocket to reach. Must be `spotcast/recently_played`.

### `limit` (int)

*Optional*

The maximum number of entries to return. Defaults to `20`. Spotify keeps only the last 50 plays, so a long session from one playlist can leave fewer entries than the limit.

### `account` (str)

*Optional*

The `entry_id` of the account to use. Defaults to the default Spotcast account if not provided.

## Response

```json
{
    "id": 1,
    "type": "result",
    "success": true,
    "result": {
        "total": 2,
        "account": "01JDG07KSBTYWZGJSBJ1EW6XEF",
        "items": [
            {
                "type": "playlist",
                "uri": "spotify:playlist:37i9dQZF1E4w2FG60fR6Uj",
                "name": "Glass Beams Radio",
                "artists": [],
                "icon": null,
                "played_at": "2026-10-29T19:12:44.302Z",
                "track_uri": "spotify:track:6nPwBuTcWFj1ZmYw9eVQuT"
            },
            {
                "type": "album",
                "uri": "spotify:album:5l5m1hnH4punS1GQXgEi3T",
                "name": "Lateralus",
                "artists": ["TOOL"],
                "icon": "https://i.scdn.co/image/ab67616d0000b273ca41a947c13b78749c4953b1",
                "played_at": "2026-10-29T18:40:02.118Z",
                "track_uri": "spotify:track:55mJleti2WfWEFNFcBduhc"
            }
        ]
    }
}
```

### `id` (int)

The id provided in the request.

### `type` (str)

Always `result` on a successful request.

### `success` (bool)

`true` if the transaction was successful.

### `result` (dict)

The result of the transaction.

> #### `total` (int)
>
> The number of entries returned.
>
> #### `account` (str)
>
> The id of the account used in the query.
>
> #### `items` (list[dict])
>
> The entries, newest first. Each includes:
>
> > ##### `type` (str)
> >
> > What was played: `album`, `artist`, `playlist`, `collection` (Liked Songs), or `track` for a song played on its own. Spotify leaves podcast episodes out of the play history.
> >
> > ##### `uri` (str)
> >
> > The Spotify URI of the album, artist, playlist, collection or track, ready for the `play_media` action.
> >
> > ##### `name` (str | null)
> >
> > The name to show. Playlist names come from Spotify's internal endpoint, which also names Spotify's own playlists; it is `null` when that lookup fails or the name is otherwise unknown.
> >
> > ##### `artists` (list[str])
> >
> > The artist names, for albums and tracks. Empty for other types.
> >
> > ##### `icon` (str | null)
> >
> > The cover art URL, for albums and tracks. `null` for other types.
> >
> > ##### `played_at` (str)
> >
> > When the newest play of this entry started, in ISO 8601.
> >
> > ##### `track_uri` (str)
> >
> > The track of that newest play, to resume where the listener left off.
