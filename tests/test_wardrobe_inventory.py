import copy
import itertools
import json
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import Mock,patch
import test_api_authorization as api_fixture
from jace.engine import CognitiveEngine
from jace.memory import MemoryConflictError
from jace.reasoner import LocalReasoner
from jace.wardrobe import CATEGORIES,INVENTORY_SOURCE,validate_inventory,encode_inventory,decode_inventory,build_wardrobe_plan

ITEM={'label':'Everyday shirts','category':'tops','quantity':5,'condition':'ready','fit':'fits','use':'unused','preserve':False,'ownership':'mine'}
INVENTORY={'items':[ITEM],'minimum_ready':{c:2 if c=='tops' else 0 for c in CATEGORIES}}
def inventory(*items,**needs):
    return {'items':list(items) or [dict(ITEM)],'minimum_ready':{**INVENTORY['minimum_ready'],**needs}}

class WardrobeInventoryTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.path=Path(self.temp.name)/'memory.db'
        self.engine=CognitiveEngine(self.path,canonical_path='',reasoner=LocalReasoner())
    def tearDown(self):self.engine.close();self.temp.cleanup()
    def save(self,value=None,user='alice',**kw):
        return self.engine.save_wardrobe_inventory(user,INVENTORY if value is None else value,confirm_save=True,**kw)[0]
    def test_schema_bounds_and_explicit_consent_before_any_write(self):
        bad=[{}, {'items':[],'minimum_ready':INVENTORY['minimum_ready']}, {**INVENTORY,'extra':1},
             {**INVENTORY,'minimum_ready':{'tops':2}},inventory({**ITEM,'extra':True}),inventory({**ITEM,'label':' bad'}),
             inventory({**ITEM,'label':'A\nB'}),inventory({**ITEM,'label':'A\u202eB'}),inventory({**ITEM,'label':'x'*61}),
             inventory(ITEM,{**ITEM,'label':'EVERYDAY SHIRTS'}),inventory({**ITEM,'label':'café'},{**ITEM,'label':'cafe\u0301'}),
             inventory({**ITEM,'category':'shirts'}),inventory({**ITEM,'condition':'clean'}),inventory({**ITEM,'fit':'yes'}),
             inventory({**ITEM,'use':'sometimes'}),inventory({**ITEM,'preserve':1}),inventory({**ITEM,'ownership':'family'}),
             inventory(*[{**ITEM,'label':str(n)} for n in range(31)]),inventory(*[{**ITEM,'label':str(n),'quantity':100} for n in range(4)])]
        for n in (-1,0,101,True,1.0,10**1000):bad.append(inventory({**ITEM,'quantity':n}))
        for n in (-1,51,True,1.0):bad.append(inventory(tops=n))
        for value in bad:
            with self.subTest(value=str(value)[:120]),self.assertRaises(ValueError):self.save(value)
        for consent in (False,None,1,'true'):
            with self.assertRaises(ValueError):self.engine.save_wardrobe_inventory('alice',INVENTORY,confirm_save=consent)
        self.assertEqual(self.engine.list_memories('alice'),[])
        self.assertEqual(self.engine.memory.connection.execute('SELECT COUNT(*) FROM memory_audit').fetchone()[0],0)
    def test_inventory_copies_caller_and_preserves_unicode_roundtrip(self):
        value=inventory({**ITEM,'label':'કપડાં'});normalized=validate_inventory(value);value['items'][0]['quantity']=1
        self.assertEqual(normalized['items'][0]['quantity'],5)
        m=self.save(normalized);self.assertEqual(decode_inventory(m),normalized)
        self.assertEqual(json.loads(encode_inventory(normalized))['inventory'],normalized)
    def test_surplus_review_budget_never_removes_declared_minimum(self):
        value=inventory({**ITEM,'label':'First','quantity':3},{**ITEM,'label':'Second','quantity':4},tops=5)
        plan=build_wardrobe_plan(value)
        self.assertEqual([s['possible_surplus_review_units'] for s in plan['item_steps']],[2,0])
        self.assertEqual(plan['categories'][0],{'category':'tops','minimum_ready':5,'owned_ready_units':7,'shortfall_units':0})
        self.assertIn('not a donation or disposal recommendation',plan['item_steps'][0]['instruction'])
        self.assertEqual(plan['item_steps'][1]['decision'],'keep_for_declared_needs')
        self.assertEqual(plan['summary']['declared_total_units'],7)
        self.assertFalse(plan['actions_executed']);self.assertIsNone(plan['action'])
        shortage=build_wardrobe_plan(inventory(tops=8));self.assertEqual(shortage['categories'][0]['shortfall_units'],3)
        self.assertEqual(shortage['item_steps'][0]['possible_surplus_review_units'],0)
    def test_all_typed_combinations_conservative_with_overlapping_counts(self):
        for owner,condition,fit,use,preserve in itertools.product(('mine','shared','others','uncertain'),('ready','repair','uncertain'),('fits','does_not_fit','uncertain'),('regular','occasional','unused','uncertain'),(False,True)):
            item={**ITEM,'ownership':owner,'condition':condition,'fit':fit,'use':use,'preserve':preserve}
            plan=build_wardrobe_plan(inventory(item,tops=0));step=plan['item_steps'][0]
            is_ready=owner=='mine' and condition=='ready' and fit=='fits'
            self.assertEqual(plan['summary']['owned_ready_units'],5 if is_ready else 0)
            self.assertEqual(plan['summary']['protected_units'],5 if preserve else 0)
            if owner!='mine':self.assertEqual(step['decision'],'ownership_review')
            elif preserve:self.assertEqual(step['decision'],'preserve')
            if step['possible_surplus_review_units']:
                self.assertTrue(is_ready and use=='unused' and not preserve)
            self.assertIsNone(plan['action'])
    def test_owned_scoped_saved_plan_without_reasoner_or_learning(self):
        m=self.save(memory_scope='home');before=self.engine.memory.connection.execute('SELECT COUNT(*) FROM memory_audit').fetchone()[0]
        self.engine.reasoner=Mock();self.engine.reasoner.respond.side_effect=AssertionError('provider not permitted')
        result=self.engine.plan_wardrobe('alice',memory_scope='home',inventory_memory_id=m.memory_id,expected_inventory_revision=m.revision)
        self.assertEqual(result['inventory_applied'],INVENTORY);self.assertEqual(result['inventory_memory'],m.to_dict())
        self.assertIn('unverified sample',result['grounding']);self.engine.reasoner.respond.assert_not_called()
        self.assertEqual(self.engine.memory.connection.execute('SELECT COUNT(*) FROM memory_audit').fetchone()[0],before)
        for user,scope in [('bob','home'),('alice','other')]:
            with self.assertRaises(LookupError):self.engine.plan_wardrobe(user,memory_scope=scope,inventory_memory_id=m.memory_id)
        self.assertEqual(self.engine.plan_wardrobe('bob',memory_scope='home')['status'],'needs_inventory')
    def test_multiple_malformed_and_plain_memories_never_guessed(self):
        self.engine.remember('alice',encode_inventory(INVENTORY));self.assertEqual(self.engine.plan_wardrobe('alice')['status'],'needs_inventory')
        first=self.save();second=self.save();result=self.engine.plan_wardrobe('alice')
        self.assertEqual(result['status'],'choose_inventory');self.assertEqual(result['item_steps'],[])
        self.engine.memory.connection.execute('UPDATE memories SET content=? WHERE id=?',('{"version":1,"inventory":{}}',first.memory_id));self.engine.memory.connection.commit()
        with self.assertRaises(ValueError):self.engine.plan_wardrobe('alice')
        self.assertEqual(self.engine.plan_wardrobe('alice',inventory_memory_id=second.memory_id)['status'],'planned')
    def test_expiry_deletion_and_type_boundary(self):
        m=self.save(expires_at='2027-01-01T00:00:00Z')
        with patch('jace.engine.recall_time',return_value=m.expires_at):
            self.assertEqual(self.engine.plan_wardrobe('alice')['status'],'needs_inventory')
            with self.assertRaises(LookupError):self.engine.plan_wardrobe('alice',inventory_memory_id=m.memory_id)
        with self.assertRaises(ValueError):self.engine.correct_memory('alice',m.memory_id,'Free text')
        ordinary=self.engine.remember('alice','Ordinary record')[0]
        with self.assertRaises(ValueError):self.engine.update_wardrobe_inventory('alice',ordinary.memory_id,INVENTORY,expected_revision=ordinary.revision,confirm_save=True)
        self.engine.forget_memory('alice',m.memory_id,confirm_delete=True)
        with self.assertRaises(LookupError):self.engine.plan_wardrobe('alice',inventory_memory_id=m.memory_id)
        self.assertIsNotNone(self.engine.memory.get_owned('alice',ordinary.memory_id))
    def test_revision_checks_preserve_expiry_and_reject_stale_plan(self):
        m=self.save(memory_scope='home',expires_at='2027-01-01T00:00:00Z')
        updated=self.engine.update_wardrobe_inventory('alice',m.memory_id,inventory(tops=4),expected_revision=m.revision,confirm_save=True)[0]
        self.assertEqual(updated.expires_at,m.expires_at);self.assertEqual(updated.memory_scope,'home')
        with self.assertRaises(MemoryConflictError):self.engine.update_wardrobe_inventory('alice',m.memory_id,INVENTORY,expected_revision=m.revision,confirm_save=True)
        with self.assertRaises(MemoryConflictError):self.engine.plan_wardrobe('alice',memory_scope='home',inventory_memory_id=m.memory_id,expected_inventory_revision=m.revision)
        with self.assertRaises(ValueError):self.engine.plan_wardrobe('alice',expected_inventory_revision=updated.revision)
        for bad in (None,True,'0'*63,'a'*64+'\n'):
            with self.assertRaises(ValueError):self.engine.update_wardrobe_inventory('alice',m.memory_id,INVENTORY,expected_revision=bad,confirm_save=True)
    def test_graph_failure_rolls_back_save_and_update(self):
        with patch.object(self.engine.graph,'add_memory',side_effect=RuntimeError('fixture')):
            with self.assertRaises(RuntimeError):self.save()
        self.assertEqual(self.engine.list_memories('alice'),[])
        m=self.save();before=list(self.engine.memory.connection.execute('SELECT * FROM memory_audit'))
        with patch.object(self.engine.graph,'add_memory',side_effect=RuntimeError('fixture')):
            with self.assertRaises(RuntimeError):self.engine.update_wardrobe_inventory('alice',m.memory_id,inventory(tops=4),expected_revision=m.revision,confirm_save=True)
        self.assertEqual(self.engine.memory.get_owned('alice',m.memory_id),m)
        self.assertEqual(list(self.engine.memory.connection.execute('SELECT * FROM memory_audit')),before)
        self.assertEqual(self.engine.memory.connection.execute('SELECT content FROM graph_nodes WHERE node_id=?',(f'memory:{m.memory_id}',)).fetchone()[0],m.content)
    def test_filter_altered_labels_roll_back_instead_of_saving_malformed_json(self):
        # Deliberately synthetic marker, not a credential.
        value=inventory({**ITEM,'label':'password=synthetic-fixture'})
        with self.assertRaises(ValueError):self.save(value)
        self.assertEqual(self.engine.list_memories('alice'),[])
        self.assertEqual(self.engine.memory.connection.execute('SELECT COUNT(*) FROM memory_audit').fetchone()[0],0)
        m=self.save();before=list(self.engine.memory.connection.execute('SELECT * FROM memory_audit'))
        with self.assertRaises(ValueError):self.engine.update_wardrobe_inventory('alice',m.memory_id,value,expected_revision=m.revision,confirm_save=True)
        self.assertEqual(self.engine.memory.get_owned('alice',m.memory_id),m)
        self.assertEqual(list(self.engine.memory.connection.execute('SELECT * FROM memory_audit')),before)

    def test_two_engine_revision_update_exactly_one_wins(self):
        m=self.save();other=CognitiveEngine(self.path,canonical_path='',reasoner=LocalReasoner());barrier=threading.Barrier(2);results=[]
        def update(engine,n):
            barrier.wait()
            try:engine.update_wardrobe_inventory('alice',m.memory_id,inventory(tops=n),expected_revision=m.revision,confirm_save=True);results.append('ok')
            except MemoryConflictError:results.append('conflict')
        try:
            threads=[threading.Thread(target=update,args=(engine,n)) for engine,n in [(self.engine,1),(other,3)]]
            for t in threads:t.start()
            for t in threads:t.join(3);self.assertFalse(t.is_alive())
            self.assertCountEqual(results,['ok','conflict'])
        finally:other.close()
    def test_bounded_default_discovery_explicit_id_and_bad_stored_schema(self):
        for _ in range(26):m=self.save()
        with self.assertRaises(ValueError):self.engine.plan_wardrobe('alice')
        self.assertEqual(self.engine.plan_wardrobe('alice',inventory_memory_id=m.memory_id)['status'],'planned')
        for content in ('{"version":true,"inventory":{}}','{"version":1,"version":1,"inventory":{}}','x'*10001):
            self.engine.memory.connection.execute('UPDATE memories SET content=? WHERE id=?',(content,m.memory_id));self.engine.memory.connection.commit()
            with self.assertRaises(ValueError):self.engine.plan_wardrobe('alice',inventory_memory_id=m.memory_id)

class WardrobeAPITests(unittest.TestCase):
    setUp=api_fixture.ApiAuthorizationTests.setUp
    tearDown=api_fixture.ApiAuthorizationTests.tearDown
    request=api_fixture.ApiAuthorizationTests.request
    def test_actual_api_create_plan_conflict_and_owner_boundaries(self):
        self.assertEqual(self.request('/health')[1]['wardrobe_planner_protocol'],1)
        body={'user_id':'alice','memory_scope':'home','inventory':INVENTORY,'confirm_save':True}
        self.assertEqual(self.request('/v1/wardrobe-inventories','POST',body,api_fixture.BOB_TOKEN)[0],403)
        status,data,_=self.request('/v1/wardrobe-inventories','POST',body,api_fixture.ALICE_TOKEN);self.assertEqual(status,201);m=data['memory']
        plan={'user_id':'alice','memory_scope':'home','inventory_memory_id':m['memory_id'],'expected_inventory_revision':m['revision']}
        self.assertEqual(self.request('/v1/plans/wardrobe','POST',plan,api_fixture.ALICE_TOKEN)[0],200)
        self.assertEqual(self.request('/v1/plans/wardrobe','POST',{**plan,'expected_inventory_revision':'0'*64},api_fixture.ALICE_TOKEN)[0],409)
        for bad in ({**plan,'scope':'home'},{**plan,'inventory_memory_id':None},{**plan,'expected_inventory_revision':None}):
            self.assertEqual(self.request('/v1/plans/wardrobe','POST',bad,api_fixture.ALICE_TOKEN)[0],400)
        change={'memory_id':m['memory_id'],'inventory':inventory(tops=3),'expected_revision':m['revision'],'confirm_save':True}
        self.assertEqual(self.request('/v1/wardrobe-inventories','PATCH',change,api_fixture.BOB_TOKEN)[0],404)
        self.assertEqual(self.request('/v1/wardrobe-inventories','PATCH',change,api_fixture.ALICE_TOKEN)[0],200)
        self.assertEqual(self.request('/v1/wardrobe-inventories','PATCH',change,api_fixture.ALICE_TOKEN)[0],409)
        self.assertEqual(self.request('/v1/memory','PATCH',{'memory_id':m['memory_id'],'content':'Not typed'},api_fixture.ALICE_TOKEN)[0],400)
    def test_actual_api_confirm_and_unknown_fields_fail_closed(self):
        for body in ({'inventory':INVENTORY},{'inventory':INVENTORY,'confirm_save':1},{'inventory':INVENTORY,'confirm_save':True,'scope':'home'}):
            self.assertEqual(self.request('/v1/wardrobe-inventories','POST',body,api_fixture.ALICE_TOKEN)[0],400)
        self.assertEqual(len(self.engine.list_memories('alice')),1)

if __name__=='__main__':unittest.main()
