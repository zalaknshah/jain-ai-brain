import unittest
from unittest.mock import patch
from jace import fresh_private_study as api
from jace._fresh_study import consumer

class BoundaryTests(unittest.TestCase):
    def test_exact_consumer_identity(self):
        self.assertIs(api.consume, consumer.consume)
        self.assertIs(api.ExpectedPins, consumer.ExpectedPins)
        self.assertIs(api.StudyDeclaration, consumer.StudyDeclaration)

    def test_no_implicit_source_or_consent(self):
        with patch.object(consumer, '_Snapshot') as snapshot:
            with self.assertRaises(consumer.ConsumerError):
                api.consume('/not-opened', pins=None, declaration=None)
            snapshot.assert_not_called()

    def test_public_surface(self):
        self.assertEqual(set(api.__all__), {'ConsumerError', 'ExpectedPins', 'StudyDeclaration', 'consume'})
