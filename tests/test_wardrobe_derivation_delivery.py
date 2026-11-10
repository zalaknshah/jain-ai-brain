"""Delivery/lifecycle checks for explicit declared-inventory derivations."""
import copy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

import test_api_authorization as api_fixture
from jace.engine import CognitiveEngine
from jace.memory import MemoryConflictError
from jace.models import CanonicalEntry
from jace.reasoner import LocalReasoner
from jace.wardrobe import build_wardrobe_plan

CATEGORIES = ('tops','bottoms','outerwear','footwear','other')
INVENTORY = {'items':[
    {'label':'Original fictional shirts','category':'tops','quantity':3,'condition':'ready',
     'fit':'fits','use':'unused','preserve':False,'ownership':'mine'},
    {'label':'Original fictional preserved shirts','category':'tops','quantity':4,'condition':'ready',
     'fit':'fits','use':'regular','preserve':True,'ownership':'mine'},
], 'minimum_ready':{key:5 if key=='tops' else 0 for key in CATEGORIES}}


def digest(value):
    return hashlib.sha256(json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()).hexdigest()


class WardrobeDerivationDeliveryTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.engine=CognitiveEngine(Path(self.temp.name)/'synthetic.db',canonical_path='',reasoner=LocalReasoner())
    def tearDown(self):self.engine.close();self.temp.cleanup()
    def save(self):
        return self.engine.save_wardrobe_inventory('alice',INVENTORY,confirm_save=True,memory_scope='home')[0]

    def test_opt_in_leaves_default_plan_unchanged_and_has_no_input_aliases(self):
        value=copy.deepcopy(INVENTORY);original=copy.deepcopy(value)
        baseline=build_wardrobe_plan(value)
        explained=build_wardrobe_plan(value,include_derivation=True)
        trace=explained.pop('derivation')
        self.assertEqual(explained,baseline);self.assertEqual(value,original)
        self.assertEqual(trace['inventory_sha256'],digest(INVENTORY))
        trace['item_rules'][0]['declared_fields']['use']='regular'
        trace['summary_contributors']['owned_ready_units'][0]['units']=99
        self.assertEqual(value,original)
        self.assertNotEqual(trace,build_wardrobe_plan(value,include_derivation=True)['derivation'])
        for invalid in (None,1,0,'true',[],{}):
            with self.subTest(invalid=invalid),self.assertRaises(ValueError):
                build_wardrobe_plan(value,include_derivation=invalid)

    def test_snapshot_bound_derivation_without_provider_or_additional_writes(self):
        saved=self.save();changes=self.engine.memory.connection.total_changes
        self.engine.reasoner=Mock();self.engine.reasoner.respond.side_effect=AssertionError('No provider')
        result=self.engine.plan_wardrobe('alice',memory_scope='home',inventory_memory_id=saved.memory_id,
            expected_inventory_revision=saved.revision,include_derivation=True)
        self.assertEqual(result['inventory_memory'],saved.to_dict())
        self.assertEqual(result['inventory_applied'],INVENTORY)
        self.assertEqual(result['derivation']['inventory_sha256'],digest(INVENTORY))
        self.assertEqual([r['allocated_units'] for r in result['derivation']['item_rules']],[2,0])
        self.assertEqual(self.engine.memory.connection.total_changes,changes)
        self.engine.reasoner.respond.assert_not_called()
        self.assertFalse(result['actions_executed']);self.assertIsNone(result['action'])

    def test_owner_scope_revision_and_expiry_checks_precede_derivation(self):
        saved=self.save();args=dict(memory_scope='home',inventory_memory_id=saved.memory_id,
            expected_inventory_revision=saved.revision,include_derivation=True)
        for user,scope in [('bob','home'),('alice','work')]:
            with self.assertRaises(LookupError):self.engine.plan_wardrobe(user,**{**args,'memory_scope':scope})
        updated=self.engine.update_wardrobe_inventory('alice',saved.memory_id,
            {**INVENTORY,'minimum_ready':{key:0 for key in CATEGORIES}},expected_revision=saved.revision,confirm_save=True)[0]
        with self.assertRaises(MemoryConflictError):self.engine.plan_wardrobe('alice',**args)
        expired=self.engine.set_memory_expiration('alice',updated.memory_id,'2020-01-01T00:00:00Z')
        with self.assertRaises(LookupError):
            self.engine.plan_wardrobe('alice',**{**args,'expected_inventory_revision':expired.revision})

    def test_no_selected_inventory_never_fabricates_a_derivation(self):
        self.assertNotIn('derivation',self.engine.plan_wardrobe('alice',include_derivation=True))
        self.save();self.save()
        result=self.engine.plan_wardrobe('alice',memory_scope='home',include_derivation=True)
        self.assertEqual(result['status'],'choose_inventory');self.assertNotIn('derivation',result)
        for invalid in (None,1,'true'):
            with self.assertRaises(ValueError):self.engine.plan_wardrobe('absent',include_derivation=invalid)

    def test_output_limits_reject_without_partial_plan_or_writes(self):
        with patch('jace.wardrobe.MAX_EXPLAINED_PLAN_BYTES',100):
            with self.assertRaisesRegex(ValueError,'output limit'):
                build_wardrobe_plan(INVENTORY,include_derivation=True)
        saved=self.save();changes=self.engine.memory.connection.total_changes
        large=[CanonicalEntry(entry_id=str(i),title='Original fixture',principle='Original fictional detail. '*800,
              guidance='Synthetic only',source='Original test author',tags=[]) for i in range(5)]
        with patch.object(self.engine.canonical,'search',return_value=large):
            with self.assertRaisesRegex(ValueError,'explained wardrobe plan exceeds'):
                self.engine.plan_wardrobe('alice',memory_scope='home',inventory_memory_id=saved.memory_id,
                    expected_inventory_revision=saved.revision,include_derivation=True)
        self.assertEqual(self.engine.memory.connection.total_changes,changes)


class WardrobeDerivationApiTests(unittest.TestCase):
    setUp=api_fixture.ApiAuthorizationTests.setUp
    tearDown=api_fixture.ApiAuthorizationTests.tearDown
    request=api_fixture.ApiAuthorizationTests.request

    def test_optional_authenticated_delivery_and_invalid_types(self):
        self.assertEqual(self.request('/health')[1]['wardrobe_derivation_protocol'],1)
        saved=self.engine.save_wardrobe_inventory('alice',INVENTORY,confirm_save=True,memory_scope='home')[0]
        body={'memory_scope':'home','inventory_memory_id':saved.memory_id,'expected_inventory_revision':saved.revision}
        status,ordinary,_=self.request('/v1/plans/wardrobe','POST',body,api_fixture.ALICE_TOKEN)
        self.assertEqual(status,200);self.assertNotIn('derivation',ordinary)
        changes=self.engine.memory.connection.total_changes
        status,explained,_=self.request('/v1/plans/wardrobe','POST',{**body,'include_derivation':True},api_fixture.ALICE_TOKEN)
        self.assertEqual(status,200);self.assertEqual(explained['derivation']['inventory_sha256'],digest(INVENTORY))
        self.assertEqual(explained['inventory_memory'],saved.to_dict())
        self.assertEqual(self.engine.memory.connection.total_changes,changes)
        for invalid in (None,1,'true',{},[]):
            self.assertEqual(self.request('/v1/plans/wardrobe','POST',{**body,'include_derivation':invalid},api_fixture.ALICE_TOKEN)[0],400)
        self.assertEqual(self.request('/v1/plans/wardrobe','POST',{**body,'include_derivation':True})[0],401)
        self.assertEqual(self.request('/v1/plans/wardrobe','POST',{**body,'include_derivation':True,'user_id':'alice'},api_fixture.BOB_TOKEN)[0],403)
        self.assertEqual(self.request('/v1/plans/wardrobe','POST',{**body,'include_derivation':True,'expected_inventory_revision':'f'*64},api_fixture.ALICE_TOKEN)[0],409)


if __name__=='__main__':unittest.main()
