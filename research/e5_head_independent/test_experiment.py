import unittest
import numpy as np
import experiment as e
class Checks(unittest.TestCase):
 def test_softmax(self):
  q=e.softmax(np.array([[1000.,1001.]]));self.assertAlmostEqual(q.sum(),1);self.assertGreater(q[0,1],q[0,0])
 def test_abstain(self):
  r=[{'id':'a','language':'en','label':None}];o=e.evaluate(np.array([[.8,.04,.04,.04,.04,.04]]),r,(.9,0));self.assertEqual(o['overall']['abstentions'],1)
 def test_false_accept(self):
  r=[{'id':'a','language':'gu','label':None}];o=e.evaluate(np.array([[.8,.04,.04,.04,.04,.04]]),r,(.5,0));self.assertEqual(o['per_language']['gu']['unsupported_false_accepts'],1)
 def test_train(self):
  x=np.eye(6);rows=[{'label':l} for l in e.LABELS];w,b,loss=e.fit(x,rows);self.assertLess(loss[1],loss[0]);self.assertTrue(np.array_equal(np.argmax(x@w+b,axis=1),np.arange(6)))
 def test_split_leak(self):
  r=[{'id':'a','family':'fam','text':'example'}]
  with self.assertRaises(AssertionError):e.split_check(r,r)
 def test_dev_prefer_abstain_for_unknown(self):
  cutoff=e.tune(np.array([[.8,.04,.04,.04,.04,.04]]),[{'id':'a','language':'hi','label':None}]);self.assertGreater(cutoff[0],.8)
 def test_data(self):
  a=e.read('train.json');b=e.read('dev.json');e.validate(a,True);e.validate(b);e.split_check(a,b)
if __name__=='__main__':unittest.main()
