import unittest
from evaluate_frozen import validate_test
LABELS=['noninjury','restraint','perspectives','conditional','provenance','consent']
def rows():
 out=[]
 for i,label in enumerate([l for l in LABELS for _ in range(2)]+[None]*12):
  for lang in ['en','hi','gu']:out.append({'id':f'{i}-{lang}','family':f'f{i}','language':lang,'label':label,'text':f'invented fixture {i} {lang}'})
 return out
class Check(unittest.TestCase):
 def test_valid(self):self.assertEqual(len(validate_test(rows())),24)
 def test_missing(self):
  with self.assertRaises(ValueError):validate_test(rows()[:-1])
 def test_family_label(self):
  x=rows();x[0]['label']=None
  with self.assertRaises(ValueError):validate_test(x)
 def test_language(self):
  x=rows();x[0]['language']='hi'
  with self.assertRaises(ValueError):validate_test(x)
 def test_balance(self):
  x=rows()
  for r in x[:3]:r['label']='consent'
  with self.assertRaises(ValueError):validate_test(x)
 def test_duplicate_id(self):
  x=rows();x[0]['id']=x[1]['id']
  with self.assertRaises(AssertionError):validate_test(x)
if __name__=='__main__':unittest.main()
