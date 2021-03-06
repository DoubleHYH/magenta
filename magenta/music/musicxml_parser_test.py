# Copyright 2016 Google Inc. All Rights Reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#    http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
"""Test to ensure correct import of MusicXML."""

from collections import defaultdict
import os.path
import tempfile

# internal imports

import tensorflow as tf

from magenta.common import testing_lib as common_testing_lib
from magenta.music import musicxml_parser
from magenta.music import musicxml_reader
from magenta.music import sequences_lib
from magenta.music import testing_lib
from magenta.protobuf import music_pb2


class MusicXMLParserTest(tf.test.TestCase):
  """Class to test the MusicXML parser use cases.

  self.flute_scale_filename contains an F-major scale of 8 quarter notes each

  self.clarinet_scale_filename contains a F-major scale of 8 quarter notes
  each appearing as written pitch. This means the key is written as
  G-major but sounds as F-major. The MIDI pitch numbers must be transposed
  to be input into Magenta

  self.band_score_filename contains a number of instruments in written
  pitch. The score has two time signatures (6/8 and 2/4) and two sounding
  keys (Bb-major and Eb major). The file also contains chords and
  multiple voices (see Oboe part in measure 57), as well as dynamics,
  articulations, slurs, ties, hairpins, grace notes, tempo changes,
  and multiple barline types (double, repeat)

  self.compressed_filename contains the same content as
  self.flute_scale_filename, but compressed in MXL format

  self.rhythm_durations_filename contains a variety of rhythms (long, short,
  dotted, tuplet, and dotted tuplet) to test the computation of rhythmic
  ratios.

  self.atonal_transposition_filename contains a change of instrument
  from a non-transposing (Flute) to transposing (Bb Clarinet) in a score
  with no key / atonal. This ensures that transposition works properly when
  no key signature is found (Issue #355)

  self.st_anne_filename contains a 4-voice piece written in two parts.
  """

  def setUp(self):
    self.maxDiff = None

    self.steps_per_quarter = 4

    self.flute_scale_filename = os.path.join(
        tf.resource_loader.get_data_files_path(),
        'testdata/flute_scale.xml')

    self.clarinet_scale_filename = os.path.join(
        tf.resource_loader.get_data_files_path(),
        'testdata/clarinet_scale.xml')

    self.band_score_filename = os.path.join(
        tf.resource_loader.get_data_files_path(),
        'testdata/el_capitan.xml')

    self.compressed_filename = os.path.join(
        tf.resource_loader.get_data_files_path(),
        'testdata/flute_scale.mxl')

    self.multiple_rootfile_compressed_filename = os.path.join(
        tf.resource_loader.get_data_files_path(),
        'testdata/flute_scale_with_png.mxl')

    self.rhythm_durations_filename = os.path.join(
        tf.resource_loader.get_data_files_path(),
        'testdata/rhythm_durations.xml')

    self.st_anne_filename = os.path.join(
        tf.resource_loader.get_data_files_path(),
        'testdata/st_anne.xml')

    self.atonal_transposition_filename = os.path.join(
        tf.resource_loader.get_data_files_path(),
        'testdata/atonal_transposition_change.xml')

  def checkmusicxmlandsequence(self, musicxml, sequence_proto):
    """Compares MusicXMLDocument object against a sequence proto.

    Args:
      musicxml: A MusicXMLDocument object.
      sequence_proto: A tensorflow.magenta.Sequence proto.
    """
    # Test time signature changes.
    self.assertEqual(len(musicxml.get_time_signatures()),
                     len(sequence_proto.time_signatures))
    for musicxml_time, sequence_time in zip(musicxml.get_time_signatures(),
                                            sequence_proto.time_signatures):
      self.assertEqual(musicxml_time.numerator, sequence_time.numerator)
      self.assertEqual(musicxml_time.denominator, sequence_time.denominator)
      self.assertAlmostEqual(musicxml_time.time_position, sequence_time.time)

    # Test key signature changes.
    self.assertEqual(len(musicxml.get_key_signatures()),
                     len(sequence_proto.key_signatures))
    for musicxml_key, sequence_key in zip(musicxml.get_key_signatures(),
                                          sequence_proto.key_signatures):

      if musicxml_key.mode == 'major':
        mode = 0
      elif musicxml_key.mode == 'minor':
        mode = 1

      # The Key enum in music.proto does NOT follow MIDI / MusicXML specs
      # Convert from MIDI / MusicXML key to music.proto key
      music_proto_keys = [11, 6, 1, 8, 3, 10, 5, 0, 7, 2, 9, 4, 11, 6, 1]
      key = music_proto_keys[musicxml_key.key + 7]
      self.assertEqual(key, sequence_key.key)
      self.assertEqual(mode, sequence_key.mode)
      self.assertAlmostEqual(musicxml_key.time_position, sequence_key.time)

    # Test tempos.
    musicxml_tempos = musicxml.get_tempos()
    self.assertEqual(len(musicxml_tempos),
                     len(sequence_proto.tempos))
    for musicxml_tempo, sequence_tempo in zip(
        musicxml_tempos, sequence_proto.tempos):
      self.assertAlmostEqual(musicxml_tempo.qpm, sequence_tempo.qpm)
      self.assertAlmostEqual(musicxml_tempo.time_position,
                             sequence_tempo.time)

    # Test parts/instruments.
    seq_parts = defaultdict(list)
    for seq_note in sequence_proto.notes:
      seq_parts[seq_note.part].append(seq_note)

    self.assertEqual(len(musicxml.parts), len(seq_parts))
    for musicxml_part, seq_part_id in zip(
        musicxml.parts, sorted(seq_parts.keys())):

      seq_instrument_notes = seq_parts[seq_part_id]
      musicxml_notes = []
      for musicxml_measure in musicxml_part.measures:
        for musicxml_note in musicxml_measure.notes:
          if not musicxml_note.is_rest:
            musicxml_notes.append(musicxml_note)

      self.assertEqual(len(musicxml_notes), len(seq_instrument_notes))
      for musicxml_note, sequence_note in zip(musicxml_notes,
                                              seq_instrument_notes):
        self.assertEqual(musicxml_note.pitch[1], sequence_note.pitch)
        self.assertEqual(musicxml_note.velocity, sequence_note.velocity)
        self.assertAlmostEqual(musicxml_note.note_duration.time_position,
                               sequence_note.start_time)
        self.assertAlmostEqual(musicxml_note.note_duration.time_position
                               + musicxml_note.note_duration.seconds,
                               sequence_note.end_time)
        # Check that the duration specified in the MusicXML and the
        # duration float match to within +/- 1 (delta = 1)
        # Delta is used because duration in MusicXML is always an integer
        # For example, a 3:2 half note might have a durationfloat of 341.333
        # but would have the 1/3 distributed in the MusicXML as
        # 341.0, 341.0, 342.0.
        # Check that (3 * 341.333) = (341 + 341 + 342) is true by checking
        # that 341.0 and 342.0 are +/- 1 of 341.333
        self.assertAlmostEqual(
            musicxml_note.note_duration.duration,
            musicxml_note.state.divisions * 4
            * musicxml_note.note_duration.duration_float(),
            delta=1)

  def checkmusicxmltosequence(self, filename):
    """Test the translation from MusicXML to Sequence proto."""
    source_musicxml = musicxml_parser.MusicXMLDocument(filename)
    sequence_proto = musicxml_reader.musicxml_to_sequence_proto(source_musicxml)
    self.checkmusicxmlandsequence(source_musicxml, sequence_proto)

  def checkFMajorScale(self, filename):
    """Verify MusicXML scale file.

    Verify that it contains the correct pitches (sounding pitch) and durations.

    Args:
      filename: file to test.
    """

    # Expected QuantizedSequence
    # Sequence tuple = (midi_pitch, velocity, start_seconds, end_seconds)
    expected_quantized_sequence = sequences_lib.QuantizedSequence()
    expected_quantized_sequence.steps_per_quarter = self.steps_per_quarter
    expected_quantized_sequence.qpm = 120.0
    expected_quantized_sequence.time_signature = (
        sequences_lib.QuantizedSequence.TimeSignature(numerator=4,
                                                      denominator=4))
    testing_lib.add_quantized_track_to_sequence(
        expected_quantized_sequence, 0,
        [
            (65, 64, 0, 4), (67, 64, 4, 8), (69, 64, 8, 12),
            (70, 64, 12, 16), (72, 64, 16, 20), (74, 64, 20, 24),
            (76, 64, 24, 28), (77, 64, 28, 32)
        ]
    )

    # Convert MusicXML to QuantizedSequence
    source_musicxml = musicxml_parser.MusicXMLDocument(filename)
    sequence_proto = musicxml_reader.musicxml_to_sequence_proto(source_musicxml)
    quantized = sequences_lib.QuantizedSequence()
    quantized.from_note_sequence(sequence_proto, self.steps_per_quarter)

    # Check equality
    self.assertEqual(expected_quantized_sequence, quantized)

  def testsimplemusicxmltosequence(self):
    """Test the simple flute scale MusicXML file."""
    self.checkmusicxmltosequence(self.flute_scale_filename)
    self.checkFMajorScale(self.flute_scale_filename)

  def testcomplexmusicxmltosequence(self):
    """Test the complex band score MusicXML file."""
    self.checkmusicxmltosequence(self.band_score_filename)

  def testtransposedxmltosequence(self):
    """Test the translation from transposed MusicXML to Sequence proto.

    Compare a transposed MusicXML file (clarinet) to an identical untransposed
    sequence (flute).
    """
    untransposed_musicxml = musicxml_parser.MusicXMLDocument(
        self.flute_scale_filename)
    transposed_musicxml = musicxml_parser.MusicXMLDocument(
        self.clarinet_scale_filename)
    untransposed_proto = musicxml_reader.musicxml_to_sequence_proto(
        untransposed_musicxml)
    self.checkmusicxmlandsequence(transposed_musicxml, untransposed_proto)
    self.checkFMajorScale(self.clarinet_scale_filename)

  def testcompressedxmltosequence(self):
    """Test the translation from compressed MusicXML to Sequence proto.

    Compare a compressed MusicXML file to an identical uncompressed sequence.
    """
    uncompressed_musicxml = musicxml_parser.MusicXMLDocument(
        self.flute_scale_filename)
    compressed_musicxml = musicxml_parser.MusicXMLDocument(
        self.compressed_filename)
    uncompressed_proto = musicxml_reader.musicxml_to_sequence_proto(
        uncompressed_musicxml)
    self.checkmusicxmlandsequence(compressed_musicxml, uncompressed_proto)
    self.checkFMajorScale(self.flute_scale_filename)

  def testmultiplecompressedxmltosequence(self):
    """Test the translation from compressed MusicXML with multiple rootfiles.

    The example MXL file contains a MusicXML file of the Flute F Major scale,
    as well as the PNG rendering of the score contained within the single MXL
    file.
    """
    uncompressed_musicxml = musicxml_parser.MusicXMLDocument(
        self.flute_scale_filename)
    compressed_musicxml = musicxml_parser.MusicXMLDocument(
        self.multiple_rootfile_compressed_filename)
    uncompressed_proto = musicxml_reader.musicxml_to_sequence_proto(
        uncompressed_musicxml)
    self.checkmusicxmlandsequence(compressed_musicxml, uncompressed_proto)
    self.checkFMajorScale(self.flute_scale_filename)

  def testrhythmdurationsxmltosequence(self):
    """Test the rhythm durations MusicXML file."""
    self.checkmusicxmltosequence(self.rhythm_durations_filename)

  def testFluteScale(self):
    """Verify properties of the flute scale."""
    ns = musicxml_reader.musicxml_file_to_sequence_proto(
        self.flute_scale_filename)
    expected_ns = common_testing_lib.parse_test_proto(
        music_pb2.NoteSequence,
        """
        ticks_per_quarter: 220
        time_signatures: {
          numerator: 4
          denominator: 4
        }
        tempos: {
          qpm: 120
        }
        key_signatures: {
          key: F
        }
        source_info: {
          source_type: SCORE_BASED
          encoding_type: MUSIC_XML
          parser: MAGENTA_MUSIC_XML
        }
        part_infos {
          part: 0
          name: "Flute"
        }
        total_time: 4.0
        """)
    expected_pitches = [65, 67, 69, 70, 72, 74, 76, 77]
    time = 0
    for pitch in expected_pitches:
      note = expected_ns.notes.add()
      note.part = 0
      note.voice = 1
      note.pitch = pitch
      note.start_time = time
      time += .5
      note.end_time = time
      note.velocity = 64
      note.numerator = 1
      note.denominator = 4
    self.assertProtoEquals(expected_ns, ns)

  def test_atonal_transposition(self):
    """Test that transposition works when changing instrument transposition.

    This can occur within a single part in a score where the score
    has no key signature / is atonal. Examples include changing from a
    non-transposing instrument to a transposing one (ex. Flute to Bb Clarinet)
    or vice versa, or changing among transposing instruments (ex. Bb Clarinet
    to Eb Alto Saxophone).
    """
    ns = musicxml_reader.musicxml_file_to_sequence_proto(
        self.atonal_transposition_filename)
    expected_ns = common_testing_lib.parse_test_proto(
        music_pb2.NoteSequence,
        """
        ticks_per_quarter: 220
        time_signatures: {
          numerator: 4
          denominator: 4
        }
        tempos: {
          qpm: 120
        }
        key_signatures: {
        }
        part_infos {
          part: 0
          name: "Flute"
        }
        source_info: {
          source_type: SCORE_BASED
          encoding_type: MUSIC_XML
          parser: MAGENTA_MUSIC_XML
        }
        total_time: 4.0
        """)
    expected_pitches = [72, 74, 76, 77, 79, 77, 76, 74]
    time = 0
    for pitch in expected_pitches:
      note = expected_ns.notes.add()
      note.pitch = pitch
      note.start_time = time
      time += .5
      note.end_time = time
      note.velocity = 64
      note.numerator = 1
      note.denominator = 4
      note.voice = 1
    self.maxDiff = None
    self.assertProtoEquals(expected_ns, ns)

  def test_st_anne(self):
    """Verify properties of the St. Anne file.

    The file contains 2 parts and 4 voices.
    """
    ns = musicxml_reader.musicxml_file_to_sequence_proto(
        self.st_anne_filename)
    expected_ns = common_testing_lib.parse_test_proto(
        music_pb2.NoteSequence,
        """
        ticks_per_quarter: 220
        time_signatures: {
          numerator: 4
          denominator: 4
        }
        tempos: {
          qpm: 120
        }
        key_signatures: {
          key: C
        }
        source_info: {
          source_type: SCORE_BASED
          encoding_type: MUSIC_XML
          parser: MAGENTA_MUSIC_XML
        }
        part_infos {
          part: 0
          name: "Harpsichord"
        }
        part_infos {
          part: 1
          name: "Piano"
        }
        total_time: 16.0
        """)
    pitches_0_1 = [
        (67, .5),

        (64, .5),
        (69, .5),
        (67, .5),
        (72, .5),

        (72, .5),
        (71, .5),
        (72, .5),
        (67, .5),

        (72, .5),
        (67, .5),
        (69, .5),
        (66, .5),

        (67, 1.5),

        (71, .5),

        (72, .5),
        (69, .5),
        (74, .5),
        (71, .5),

        (72, .5),
        (69, .5),
        (71, .5),
        (67, .5),

        (69, .5),
        (72, .5),
        (74, .5),
        (71, .5),

        (72, 1.5),
    ]
    pitches_0_2 = [
        (60, .5),

        (60, .5),
        (60, .5),
        (60, .5),
        (64, .5),

        (62, .5),
        (62, .5),
        (64, .5),
        (64, .5),

        (64, .5),
        (64, .5),
        (64, .5),
        (62, .5),

        (62, 1.5),

        (62, .5),

        (64, .5),
        (60, .5),
        (65, .5),
        (62, .5),

        (64, .75),
        (62, .25),
        (59, .5),
        (60, .5),

        (65, .5),
        (64, .5),
        (62, .5),
        (62, .5),

        (64, 1.5),
    ]
    pitches_1_1 = [
        (52, .5),

        (55, .5),
        (57, .5),
        (60, .5),
        (60, .5),

        (57, .5),
        (55, .5),
        (55, .5),
        (60, .5),

        (60, .5),
        (59, .5),
        (57, .5),
        (57, .5),

        (59, 1.5),

        (55, .5),

        (55, .5),
        (57, .5),
        (57, .5),
        (55, .5),

        (55, .5),
        (57, .5),
        (56, .5),
        (55, .5),

        (53, .5),
        (55, .5),
        (57, .5),
        (55, .5),

        (55, 1.5),
    ]
    pitches_1_2 = [
        (48, .5),

        (48, .5),
        (53, .5),
        (52, .5),
        (57, .5),

        (53, .5),
        (55, .5),
        (48, .5),
        (48, .5),

        (45, .5),
        (52, .5),
        (48, .5),
        (50, .5),

        (43, 1.5),

        (55, .5),

        (48, .5),
        (53, .5),
        (50, .5),
        (55, .5),

        (48, .5),
        (53, .5),
        (52, .5),
        (52, .5),

        (50, .5),
        (48, .5),
        (53, .5),
        (55, .5),

        (48, 1.5),
    ]
    part_voice_instrument_program_pitches = [
        (0, 1, 1, 7, pitches_0_1),
        (0, 2, 1, 7, pitches_0_2),
        (1, 1, 2, 1, pitches_1_1),
        (1, 2, 2, 1, pitches_1_2),
    ]
    for part, voice, instrument, program, pitches in (
        part_voice_instrument_program_pitches):
      time = 0
      for pitch, duration in pitches:
        note = expected_ns.notes.add()
        note.part = part
        note.voice = voice
        note.pitch = pitch
        note.start_time = time
        time += duration
        note.end_time = time
        note.velocity = 64
        note.instrument = instrument
        note.program = program
        if duration == .5:
          note.numerator = 1
          note.denominator = 4
        if duration == .25:
          note.numerator = 1
          note.denominator = 8
        if duration == .75:
          note.numerator = 3
          note.denominator = 8
        if duration == 1.5:
          note.numerator = 3
          note.denominator = 4
    expected_ns.notes.sort(
        key=lambda note: (note.part, note.voice, note.start_time))
    ns.notes.sort(
        key=lambda note: (note.part, note.voice, note.start_time))
    self.assertProtoEquals(expected_ns, ns)

  def test_empty_part_name(self):
    """Verify that a part with an empty name can be parsed."""

    xml = r"""<?xml version="1.0" encoding="UTF-8" standalone="no"?>
      <!DOCTYPE score-partwise PUBLIC
          "-//Recordare//DTD MusicXML 3.0 Partwise//EN"
          "http://www.musicxml.org/dtds/partwise.dtd">
      <score-partwise version="3.0">
        <part-list>
          <score-part id="P1">
            <part-name/>
          </score-part>
        </part-list>
        <part id="P1">
        </part>
      </score-partwise>
    """
    with tempfile.NamedTemporaryFile() as temp_file:
      temp_file.write(xml)
      temp_file.flush()
      ns = musicxml_reader.musicxml_file_to_sequence_proto(
          temp_file.name)

    expected_ns = common_testing_lib.parse_test_proto(
        music_pb2.NoteSequence,
        """
        ticks_per_quarter: 220
        source_info: {
          source_type: SCORE_BASED
          encoding_type: MUSIC_XML
          parser: MAGENTA_MUSIC_XML
        }
        key_signatures {
          key: C
          time: 0
        }
        tempos {
          qpm: 120.0
        }
        part_infos {
          part: 0
        }
        total_time: 0.0
        """)
    self.assertProtoEquals(expected_ns, ns)

  def test_empty_part_list(self):
    """Verify that a part without a corresponding score-part can be parsed."""

    xml = r"""<?xml version="1.0" encoding="UTF-8" standalone="no"?>
      <!DOCTYPE score-partwise PUBLIC
          "-//Recordare//DTD MusicXML 3.0 Partwise//EN"
          "http://www.musicxml.org/dtds/partwise.dtd">
      <score-partwise version="3.0">
        <part id="P1">
        </part>
      </score-partwise>
    """
    with tempfile.NamedTemporaryFile() as temp_file:
      temp_file.write(xml)
      temp_file.flush()
      ns = musicxml_reader.musicxml_file_to_sequence_proto(
          temp_file.name)

    expected_ns = common_testing_lib.parse_test_proto(
        music_pb2.NoteSequence,
        """
        ticks_per_quarter: 220
        source_info: {
          source_type: SCORE_BASED
          encoding_type: MUSIC_XML
          parser: MAGENTA_MUSIC_XML
        }
        key_signatures {
          key: C
          time: 0
        }
        tempos {
          qpm: 120.0
        }
        part_infos {
          part: 0
        }
        total_time: 0.0
        """)
    self.assertProtoEquals(expected_ns, ns)

  def test_empty_doc(self):
    """Verify that an empty doc can be parsed."""

    xml = r"""<?xml version="1.0" encoding="UTF-8" standalone="no"?>
      <!DOCTYPE score-partwise PUBLIC
          "-//Recordare//DTD MusicXML 3.0 Partwise//EN"
          "http://www.musicxml.org/dtds/partwise.dtd">
      <score-partwise version="3.0">
      </score-partwise>
    """
    with tempfile.NamedTemporaryFile() as temp_file:
      temp_file.write(xml)
      temp_file.flush()
      ns = musicxml_reader.musicxml_file_to_sequence_proto(
          temp_file.name)

    expected_ns = common_testing_lib.parse_test_proto(
        music_pb2.NoteSequence,
        """
        ticks_per_quarter: 220
        source_info: {
          source_type: SCORE_BASED
          encoding_type: MUSIC_XML
          parser: MAGENTA_MUSIC_XML
        }
        key_signatures {
          key: C
          time: 0
        }
        tempos {
          qpm: 120.0
        }
        total_time: 0.0
        """)
    self.assertProtoEquals(expected_ns, ns)


if __name__ == '__main__':
  tf.test.main()
