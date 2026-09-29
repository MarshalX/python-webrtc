Media processing
================

Media is read from tracks and written to them with the APIs of browsers, as MDN documents them:

- :obj:`webrtc.MediaStreamTrackProcessor` reads a track (local or remote) as a :obj:`webrtc.ReadableStream` of
  :obj:`webrtc.VideoFrame` or :obj:`webrtc.AudioData` objects
  (`MDN <https://developer.mozilla.org/en-US/docs/Web/API/MediaStreamTrackProcessor>`__).
- :obj:`webrtc.VideoTrackGenerator` is a video track of the frames written to its :obj:`webrtc.WritableStream`
  (`MDN <https://developer.mozilla.org/en-US/docs/Web/API/VideoTrackGenerator>`__).
- :obj:`webrtc.MediaStreamTrackGenerator` is the same for audio (and video), as Chrome has it
  (`MDN <https://developer.mozilla.org/en-US/docs/Web/API/MediaStreamTrackGenerator>`__).

Frames are held until closed: close each frame read once it's used. A processor queues ``max_buffer_size`` frames
(1 of video, 10 chunks of 10 ms of audio by default) and drops the oldest when a reader is slower than the track, so
memory never grows. Media threads never wait for the GIL: Python is woken once when frames are there.

Receiving
---------

.. code-block:: python

    @pc.on('track')
    async def on_track(event):
        async for frame in webrtc.MediaStreamTrackProcessor(event.track).readable:
            rgba = bytearray(frame.allocation_size({'format': 'RGBA'}))
            await frame.copy_to(rgba, {'format': 'RGBA'})
            frame.close()

Sending
-------

.. code-block:: python

    generator = webrtc.VideoTrackGenerator()
    pc.add_track(generator.track)
    writer = generator.writable.get_writer()
    await writer.write(webrtc.VideoFrame(i420, format='I420', coded_width=640, coded_height=480, timestamp=0))

    microphone = webrtc.MediaStreamTrackGenerator('audio')
    pc.add_track(microphone)
    await microphone.writable.get_writer().write(
        webrtc.AudioData(format='s16', sample_rate=48000, number_of_frames=480, number_of_channels=1,
                         timestamp=0, data=pcm)
    )

Transforming
------------

.. code-block:: python

    processor = webrtc.MediaStreamTrackProcessor(track)
    generator = webrtc.VideoTrackGenerator()
    await processor.readable.pipe_through(webrtc.TransformStream(transformer)).pipe_to(generator.writable)
