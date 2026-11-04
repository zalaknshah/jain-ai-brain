"""Purpose/owner-bound HTTP assertions, not proof of human review or fresh consent."""
import http.client
import socket
import unittest
from unittest.mock import patch
from urllib.parse import quote

from jace.auth import ApiAuthorization

import test_owner_deletion_target as fixture

HEADER = 'X-JACE-Confirm-Owner-Delete'
VALUE = 'all-memories-graph-and-audit:alice'


class OwnerDeletionConsentTests(unittest.TestCase):
    setUp = fixture.OwnerDeletionTargetTests.setUp
    tearDown = fixture.OwnerDeletionTargetTests.tearDown
    delete = fixture.OwnerDeletionTargetTests.delete
    assert_unchanged = fixture.OwnerDeletionTargetTests.assert_unchanged

    def test_missing_or_nonexact_consent_fails_before_any_engine_work(self):
        values = [None, '', 'true', 'alice', 'all-unattributed-for-owner', str(self.alice[0].memory_id),
                  'all-memories-graph-and-audit:bob', 'all-memories-graph-and-audit:Alice',
                  'all-memories-graph-and-audit:%61lice', 'all-memories-graph-and-audit:alice ',
                  'all-memories-graph-and-audit:alice, all-memories-graph-and-audit:alice',
                  'all-memories-graph-and-audit:alice\r\n folded',
                  'all-memories:alice', 'all-memories-graph-and-audit:alice:home']
        with patch.object(self.engine, 'request_admission', wraps=self.engine.request_admission) as admission:
            for value in values:
                with self.subTest(value=value):
                    status, headers, body = self.delete(headers=[] if value is None else [(HEADER,value)])
                    self.assertEqual(status, 409)
                    self.assertEqual(body['required_header'], HEADER + ': ' + VALUE)
                    self.assertIs(body['automatic_retry'], False)
                    self.assertIn('all memory scopes', body['error'])
                    self.assertIn('expired', body['error'])
                    self.assertIn('audit', body['error'])
                    self.assertEqual(headers['Cache-Control'], 'no-store')
                    self.assert_unchanged()
            admission.assert_not_called()

    def test_duplicate_consent_never_selects_one_value(self):
        with patch.object(self.engine, 'request_admission', wraps=self.engine.request_admission) as admission:
            for first, second in [(VALUE,VALUE),(VALUE,'no'),('no',VALUE),(VALUE,''),('',VALUE)]:
                with self.subTest(first=first,second=second):
                    self.assertEqual(self.delete(headers=[(HEADER,first),(HEADER.lower(),second)])[0],409)
                    self.assert_unchanged()
            admission.assert_not_called()

    def test_consent_does_not_authorize_a_different_owner_or_origin(self):
        with patch.object(self.engine, 'request_admission', wraps=self.engine.request_admission) as admission:
            for token,status in [(None,401),('invalid',401),(fixture.BOB,403)]:
                self.assertEqual(self.delete(token=token,headers=[(HEADER,VALUE)])[0],status)
                self.assert_unchanged()
            self.assertEqual(self.delete(headers=[(HEADER,VALUE),('Origin','https://other.invalid')])[0],403)
            self.assert_unchanged()
            admission.assert_not_called()

    def test_header_name_case_is_insensitive_but_purpose_and_owner_are_exact(self):
        status,_,body=self.delete(headers=[(HEADER.lower(),VALUE)])
        self.assertEqual(status,200)
        self.assertEqual(body,{'deleted':4,'user_id':'alice'})
        self.assertEqual([item.memory_id for item in self.engine.list_memories('bob',memory_scope='home')],[self.bob.memory_id])

    def test_owner_consent_cannot_substitute_for_item_conditions(self):
        memory=self.alice[0]
        path='/v1/memory-item/'+str(memory.memory_id)
        item=[('X-JACE-Confirm-Delete',str(memory.memory_id)),
              ('X-JACE-Confirm-Audit-Cleanup','all-unattributed-for-owner'),
              ('X-JACE-If-Memory-Revision',memory.revision)]
        with patch.object(self.engine, 'request_admission', wraps=self.engine.request_admission) as admission:
            for headers in [[(HEADER,VALUE)],[(HEADER,'')],[(HEADER,VALUE),(HEADER.lower(),VALUE)]]:
                self.assertEqual(self.delete(path,headers=headers)[0],409)
                self.assert_unchanged()
            admission.assert_not_called()
        # An unrelated header still cannot grant or broaden item permission.
        # Valid explicit item conditions retain their existing behavior.
        self.assertEqual(self.delete(path,headers=[(HEADER,VALUE),*item])[0],200)
        self.assertEqual(self.engine.memory.connection.execute("SELECT COUNT(*) FROM memories WHERE user_id='alice'").fetchone()[0],3)

    def test_allowed_preflight_advertises_both_distinct_confirmation_headers(self):
        wire = b'OPTIONS /v1/memory/alice HTTP/1.1\r\nHost: localhost\r\nOrigin: http://127.0.0.1:8080\r\nConnection: close\r\n\r\n'
        with socket.create_connection(self.server.server_address,timeout=3) as client:
            client.sendall(wire)
            response=http.client.HTTPResponse(client);response.begin()
            self.assertEqual(response.status,204)
            fields={field.strip() for field in response.headers['Access-Control-Allow-Headers'].split(',')}
            self.assertIn(HEADER,fields)
            self.assertIn('X-JACE-Confirm-Delete',fields)
            response.read();response.close()
        self.assert_unchanged()

    def test_encoded_owner_assertion_is_canonical_and_not_interchangeable(self):
        owner='owner /;? é'
        self.server.authorization=ApiAuthorization({fixture.ALICE:owner,fixture.BOB:'bob'})
        self.engine.remember(owner,'I prefer quiet rooms')
        self.before=list(self.engine.memory.connection.iterdump())
        encoded=quote(owner,safe='')
        target='/v1/memory/'+encoded
        wrong=[encoded.replace('%2F','%2f'),encoded.replace('%20','+'),quote(encoded,safe=''),
               'owner /;? %C3%A9','alice',encoded+':home']
        with patch.object(self.engine, 'request_admission', wraps=self.engine.request_admission) as admission:
            for value in wrong:
                self.assertEqual(self.delete(target,headers=[(HEADER,'all-memories-graph-and-audit:'+value)])[0],409)
                self.assert_unchanged()
            admission.assert_not_called()
        self.assertEqual(self.delete(target,headers=[(HEADER,'all-memories-graph-and-audit:'+encoded)])[2],{'deleted':1,'user_id':owner})
        self.assertEqual(self.engine.memory.connection.execute("SELECT COUNT(*) FROM memories WHERE user_id='alice'").fetchone()[0],4)

    def test_valid_assertion_does_not_bypass_body_framing(self):
        with patch.object(self.engine, 'request_admission', wraps=self.engine.request_admission) as admission:
            for extra in [[('Content-Length','1')],[('Content-Length','0'),('Content-Length','0')],
                          [('Transfer-Encoding','chunked')],[('Content-Length','-1')]]:
                self.assertEqual(self.delete(headers=[(HEADER,VALUE),*extra])[0],400)
                self.assert_unchanged()
            admission.assert_not_called()

    def test_normalized_owner_path_still_requires_explicit_consent(self):
        for target in ('//v1/memory/alice','///v1/memory/alice'):
            self.assertEqual(self.delete(target)[0],409)
            self.assert_unchanged()
        self.assertEqual(self.delete('//v1/memory/alice',headers=[(HEADER,VALUE)])[0],200)


if __name__ == '__main__':
    unittest.main()
