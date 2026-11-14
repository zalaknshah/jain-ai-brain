import unittest
import numpy as np
import experiment as e
class Checks(unittest.TestCase):
 def test_softmax(self):
  q=e.softmax(np.array([[1000.,1001.]]));self.assertAlmostEqual(q.sum(),1)
 def test_train(self):
  x=np.eye(7);w,b,loss=e.fit(x,[{'label':l} for l in e.LABELS]);self.assertLess(loss[-1],loss[0]);np.testing.assert_array_equal(np.argmax(x@w+b,axis=1),np.arange(7))
 def test_unsupported_top_always_abstains(self):
  r=e.evaluate(np.array([[.01,.01,.01,.01,.01,.01,.94]]),[{'id':'a','language':'en','label':None}],(0,0));self.assertIsNone(r['predictions'][0]['selected'])
 def test_supported_false_accept_count(self):
  r=e.evaluate(np.array([[.94,.01,.01,.01,.01,.01,.01]]),[{'id':'a','language':'gu','label':None}],(0,0));self.assertEqual(r['overall']['unsupported_false_accepts'],1)
 def test_train_mean_only(self):
  t=np.eye(2);a,m=e.centered(t,np.vstack([t,[1,2]]));b,n=e.centered(t,np.vstack([t,[3,4]]));np.testing.assert_array_equal(a[:2],b[:2]);np.testing.assert_array_equal(m,n)
 def test_zero_center_refused(self):
  with self.assertRaises(ValueError):e.centered(np.eye(2),np.array([[.5,.5]]))
 def test_splits(self):
  a,b=e.load('train.json'),e.load('dev.json');e.validate(a,True);e.validate(b);e.split(a,b)
 def test_leak_refused(self):
  r=[{'id':'a','family':'f','text':'same'}]
  with self.assertRaises(AssertionError):e.split(r,r)
 def test_unknown_train_invalid(self):
  r=[{'id':'a','family':'f','language':'en','text':'invented','label':None}]
  with self.assertRaises(AssertionError):e.validate(r,True)
if __name__=='__main__':unittest.main()
