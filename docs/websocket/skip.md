# Skip

Skips forward in an account's queue, so the Nth item of [`spotcast/queue`](./queue.md) plays next in one request. Spotcast calls Spotify's next track endpoint `count` times, one call after the other, on the account's active device.

## Request

```json
{
    "id": 1,
    "type": "spotcast/skip",
    "count": 3,
    "account": "01JDG07KSBTYWZGJSBJ1EW6XEF"
}
```

### `id` (int)

*Required*

The id of the transaction. Must be an increment of the last transaction id.

### `type` (str)

*Required*

The endpoint of the WebSocket to reach. Must be `spotcast/skip`.

### `count` (int)

*Required*

The number of items to skip, from `1` to `20`. `1` plays the next item, `3` plays the third item of the queue.

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
        "skipped": 3
    }
}
```

When the first skip fails (for example when no device is active on the account), the request fails with a `PlaybackError`. When a later skip fails, Spotcast stops there and the request succeeds with the number of skips that went through.

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
> #### `skipped` (int)
>
> The number of skips that went through, at most `count`.
