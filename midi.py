from mido import Message, MidiFile, MidiTrack

mid = MidiFile()
mid.ticks_per_beat = 480

track = MidiTrack()
mid.tracks.append(track)



track.append(Message('program_change', program=25, time=0))

track.append(Message('note_on', note=62, velocity=64, time=120))
track.append(Message('note_off', time=240))

track.append(Message('note_on', note=71, velocity=64, time=0))
track.append(Message('note_off', time=480))

track.append(Message('note_on', note=71, velocity=64, time=0))
track.append(Message('note_off', time=480))

track.append(Message('note_on', note=69, velocity=64, time=0))
track.append(Message('note_off', time=480))

track.append(Message('note_on', note=71, velocity=64, time=0))
track.append(Message('note_off', time=480))

track.append(Message('note_on', note=67, velocity=64, time=0))
track.append(Message('note_off', time=480))

track.append(Message('note_on', note=62, velocity=64, time=0))
track.append(Message('note_off', time=480))

track.append(Message('note_on', note=62, velocity=64, time=0))
track.append(Message('note_off', time=480))

mid.save('.temp/song.mid')