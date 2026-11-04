"""Original synthetic source -> actual embedded JS report -> runtime export.

The JavaScript runs in a DOM harness, not a real browser or download manager.
"""
import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from jace.canonical import CanonicalStore
from jace.source_review import prepare_source_review, export_reviewed_sources, load_review_package


@unittest.skipUnless(shutil.which('node'), 'Node is required for the local review-script fixture')
class SourceReviewIntegrationTests(unittest.TestCase):
    def test_actual_generated_document_decisions_export_only_approved_records(self):
        self._exercise('integration_report')

    def test_resumed_generated_report_exports_only_approved_records(self):
        self._exercise('resume_roundtrip')

    def _exercise(self, scenario):
        root_repo=Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary)
            original=b'Approved lantern fixture. Unapproved comet fixture.'
            source=root/'fixture.txt';source.write_bytes(original)
            manifest=prepare_source_review([source],root/'draft',work='Original synthetic fixture',
                source='Operator-authored test',language='en',license_name='Operator owns this fixture',
                location='Fixture section',confirm_copy=True,chunk_words=3,overlap_words=0)
            snapshot=load_review_package(manifest)
            self.assertEqual(len(snapshot['records']),2)
            with self.assertRaises(ValueError):CanonicalStore(manifest)
            report=root/'decisions.json'
            run=subprocess.run(['node',str(root_repo/'tests/source_review_harness.js'),scenario,
                str(manifest.parent/'review.html'),str(report)],capture_output=True,text=True,timeout=10)
            self.assertEqual(run.returncode,0,run.stderr+run.stdout)
            decisions=json.loads(report.read_text())
            self.assertEqual(decisions['draft_revision'],snapshot['draft_revision'])
            self.assertEqual([row['decision'] for row in decisions['decisions']],['approve','reject'])
            self.assertNotIn(original.decode(),report.read_text())
            result=export_reviewed_sources(manifest,report,root/'runtime',confirm_export=True,
                declare_qualified_review=True,declare_rights_for_local_retrieval=True)
            self.assertEqual((result['approved_records'],result['rejected_records']), (1,1))
            store=CanonicalStore(result['manifest_path'])
            self.assertEqual([entry.principle for entry in store.all()],['Approved lantern fixture.'])
            self.assertEqual(store.search('comet'),[])
            exported=Path(result['manifest_path']).parent/'sources'/f"{snapshot['sources'][0]['sha256']}.txt"
            self.assertEqual(exported.read_bytes(),original)
            self.assertIn('pending or unreviewed text',result['warning'].lower());self.assertIn('contents are not filtered',result['warning'].lower())
            self.assertEqual(len(CanonicalStore().all()),6)  # No default activation.
            # HTML/report decisions cannot authorize a later changed draft.
            payload=json.loads(manifest.read_text());payload['records'][0]['source']='Changed attribution'
            manifest.write_text(json.dumps(payload))
            with self.assertRaises(ValueError):
                export_reviewed_sources(manifest,report,root/'stale-export',confirm_export=True,
                    declare_qualified_review=True,declare_rights_for_local_retrieval=True)
            self.assertFalse((root/'stale-export').exists())
