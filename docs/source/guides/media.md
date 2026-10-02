# Media

Media is read from tracks and written to them with the APIs of the browsers:

- {obj}`~webrtc.MediaStreamTrackProcessor` reads a track, local or remote, as a {obj}`~webrtc.ReadableStream` of
  {obj}`~webrtc.VideoFrame` or {obj}`~webrtc.AudioData` objects
  ([MDN](https://developer.mozilla.org/en-US/docs/Web/API/MediaStreamTrackProcessor)).
- {obj}`~webrtc.VideoTrackGenerator` is a video track of the frames written to its {obj}`~webrtc.WritableStream`
  ([MDN](https://developer.mozilla.org/en-US/docs/Web/API/VideoTrackGenerator)).
- {obj}`~webrtc.MediaStreamTrackGenerator` is the same for audio and video, as Chrome has it
  ([MDN](https://developer.mozilla.org/en-US/docs/Web/API/MediaStreamTrackGenerator)).

Frames hold memory until closed: close each frame once it's used. A processor queues `max_buffer_size` frames (1 of
video, 10 chunks of 10 ms of audio by default) and drops the oldest when a reader is slower than the track, so
memory never grows. Media threads never wait for the GIL: Python is woken once when frames are there.

## Tracks to start with

`webrtc.media_devices`, the {obj}`~webrtc.MediaDevices` of the library, has a synthetic camera and microphone,
handy for tests and for sending something before you have media of your own:

```python
stream = await webrtc.media_devices.get_user_media(webrtc.MediaStreamConstraints(audio=True, video=True))
for track in stream.get_tracks():
    pc.add_track(track, stream)
```

## Receiving

```python
@pc.on('track')
async def on_track(event):
    if event.track.kind != 'video':
        return
    rgba_options = webrtc.VideoFrameCopyToOptions(format='RGBA')
    processor = webrtc.MediaStreamTrackProcessor(webrtc.MediaStreamTrackProcessorInit(event.track))
    async for frame in processor.readable:
        rgba = bytearray(frame.allocation_size(rgba_options))
        await frame.copy_to(rgba, rgba_options)
        frame.close()
```

## Sending

```python
generator = webrtc.VideoTrackGenerator()
pc.add_track(generator.track)
writer = generator.writable.get_writer()
init = webrtc.VideoFrameBufferInit(format='I420', coded_width=640, coded_height=480, timestamp=0)
await writer.write(webrtc.VideoFrame(i420, init))

microphone = webrtc.MediaStreamTrackGenerator('audio')
pc.add_track(microphone)
await microphone.writable.get_writer().write(
    webrtc.AudioData(
        webrtc.AudioDataInit(
            format='s16', sample_rate=48000, number_of_frames=480, number_of_channels=1, timestamp=0, data=pcm
        )
    )
)
```

## Transforming

A processor pipes through a {obj}`~webrtc.TransformStream` into a generator, as in a browser:

```python
processor = webrtc.MediaStreamTrackProcessor(webrtc.MediaStreamTrackProcessorInit(track))
generator = webrtc.VideoTrackGenerator()
await processor.readable.pipe_through(webrtc.TransformStream(transformer)).pipe_to(generator.writable)
```

The [echo example](../examples/echo.md) is a complete one: it sends the received video back in grayscale.
