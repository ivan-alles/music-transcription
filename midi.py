import sys

import mido
from mido import Message, MidiFile, MidiTrack
import numpy as np

midi_notes = [0] * 128

midi_notes[69] = 440.0

for i in range(70, 128):
    midi_notes[i] = midi_notes[i - 1] * np.power(2, 1/12)
for i in range(68, -1, -1):
    midi_notes[i] = midi_notes[i + 1] / np.power(2, 1/12)

midi_notes = np.array(midi_notes)


def transcribe(f0_file_name):
    f0 = []
    with open(f0_file_name, 'r') as f:
        for l in f.readlines():
            l = l.replace('\n', '').replace('\r', '')
            if not l:
                continue
            f0.append([float(x) for x in l.split('\t')])

    f0 = np.array(f0)

    bpm = 240  # original song is 1/8 = 240
    sampling_interval = 0.25  # 1/8 is the atomic note

    mid = MidiFile()
    mid.ticks_per_beat = 480  # assume 1 beat is 1/8

    track = MidiTrack()
    mid.tracks.append(track)

    track.append(mido.MetaMessage('set_tempo', tempo=mido.bpm2tempo(bpm)))
    track.append(Message('program_change', program=1, time=0))


    start = 0
    sample = 0

    samples = [1]

    while start < len(f0):
        start_time = sample * sampling_interval
        end_time = None
        for end in range(start, len(f0)):
            if f0[end][0] > start_time + sampling_interval:
                end_time = f0[end - 1][0]
                break
        if end_time is None:
            break

        average_freq = max(np.median(f0[start:end, 1]), 1)
        samples.append(average_freq)

        start = end
        sample += 1

    last_note_change = 1
    for s in range(1, len(samples)):
        a, b = samples[s - 1], samples[s]
        if a > b:
            a, b = b, a

        if b / a > np.power(2, 1 / 24):
            if samples[s - 1] > 1:
                track.append(Message('note_off', time=(s - last_note_change) * mid.ticks_per_beat))
                last_note_change = s
            if samples[s] > 1:
                midi_note = np.argmin(np.abs(midi_notes - samples[s]))
                track.append(Message('note_on', note=midi_note, time=(s - last_note_change) * mid.ticks_per_beat))
                last_note_change = s


    mid.save('.temp/song.mid')

if __name__ == '__main__':
    transcribe(sys.argv[1])