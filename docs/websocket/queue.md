# Queue

Provides what is playing on an account and the tracks and podcast episodes that follow it, as the Spotify app's "Up next" shows them. Use [`spotcast/skip`](./skip.md) to jump ahead to one of them.

## Request

```json
{
    "id": 1,
    "type": "spotcast/queue",
    "limit": 10,
    "account": "01JDG07KSBTYWZGJSBJ1EW6XEF"
}
```

### `id` (int)

*Required*

The id of the transaction. Must be an increment of the last transaction id.

### `type` (str)

*Required*

The endpoint of the WebSocket to reach. Must be `spotcast/queue`.

### `limit` (int)

*Optional*

The maximum number of queued items to return, from `1` to `20`. Defaults to `10`. Spotify returns at most 20.

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
        "account": "31l77y2al5lnn7mxfrmd4bpfhqke",
        "current": {
            "uri": "spotify:track:55mJleti2WfWEFNFcBduhc",
            "id": "55mJleti2WfWEFNFcBduhc",
            "type": "track",
            "name": "Schism",
            "artists": ["TOOL"],
            "album": "Lateralus",
            "image": "https://i.scdn.co/image/ab67616d00004851ca41a947c13b78749c4953b1",
            "duration_ms": 403533
        },
        "queue": [
            {
                "uri": "spotify:track:6pWgRkpqVfxnj3WuIcJ7WP",
                "id": "6pWgRkpqVfxnj3WuIcJ7WP",
                "type": "track",
                "name": "Parabol",
                "artists": ["TOOL"],
                "album": "Lateralus",
                "image": "https://i.scdn.co/image/ab67616d00004851ca41a947c13b78749c4953b1",
                "duration_ms": 184200
            },
            {
                "uri": "spotify:episode:4rOoJ6Egrf8K2IrywzwOMk",
                "id": "4rOoJ6Egrf8K2IrywzwOMk",
                "type": "episode",
                "name": "The Making of Lateralus",
                "artists": ["Rock History Media"],
                "album": "Album Stories",
                "image": "https://i.scdn.co/image/ab6765630000f68d8b2f2c2f8c1a4d63e3b9b0a1",
                "duration_ms": 2843000
            }
        ]
    }
}
```

When nothing is playing on the account, the request still succeeds, with `current` set to `null` and an empty `queue`.

### `id` (int)

The id provided in the request.

### `type` (str)

Always `result` on a successful request.

### `success` (bool)

`true` if the transaction was successful.

### `result` (dict)

The result of the transaction.

> #### `account` (str)
>
> The id of the account used in the query.
>
> #### `current` (dict | null)
>
> The item playing now, in the same form as the `queue` items. `null` when nothing is playing.
>
> #### `queue` (list[dict])
>
> The items that play next, in order, at most `limit` of them. Each includes:
>
> > ##### `uri` (str)
> >
> > The Spotify URI of the track or episode.
> >
> > ##### `id` (str | null)
> >
> > The Spotify id of the track or episode. `null` for a local file.
> >
> > ##### `type` (str)
> >
> > `track` or `episode`.
> >
> > ##### `name` (str)
> >
> > The name of the track or episode.
> >
> > ##### `artists` (list[str])
> >
> > The artist names of a track, or the publisher of an episode's show. Empty when the show names no publisher.
> >
> > ##### `album` (str | null)
> >
> > The name of the track's album, or of the episode's show.
> >
> > ##### `image` (str | null)
> >
> > The cover art URL, sized for a list row: the smallest image at least 64 px wide, else the largest one. An episode without its own image uses its show's. `null` when there is none (a local file, for example).
> >
> > ##### `duration_ms` (int)
> >
> > The length of the track or episode, in milliseconds.
