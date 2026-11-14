import unittest
import numpy as np
import probe as p
class Check(unittest.TestCase):
 def test_fit(self):
  w,b,loss=p.fit(np.eye(2),[0,1],2);self.assertLess(loss[-1],loss[0]);np.testing.assert_array_equal(np.argmax(w+b,axis=1),[0,1])
 def test_gate_blocks(self):
  r=p.evaluate(np.array([[.9,.1]]),np.array([[.9,.02,.02,.02,.02,.02]]),[{'id':'x','language':'en','label':None}],(.5,0,0));self.assertIsNone(r['predictions'][0]['selected'])
 def test_topic_margin_blocks(self):
  r=p.evaluate(np.array([[.1,.9]]),np.array([[.3,.29,.11,.1,.1,.1]]),[{'id':'x','language':'en','label':'noninjury'}],(.5,0,.1));self.assertIsNone(r['predictions'][0]['selected'])
 def test_false_accept(self):
  r=p.evaluate(np.array([[.1,.9]]),np.array([[.9,.02,.02,.02,.02,.02]]),[{'id':'x','language':'gu','label':None}],(.5,0,0));self.assertEqual(r['overall']['unsupported_false_accepts'],1)
 def test_tune_unknown(self):
  cut=p.tune(np.array([[.1,.9]]),np.array([[.9,.02,.02,.02,.02,.02]]),[{'id':'x','language':'en','label':None}]);self.assertGreater(cut[0],.9)
if __name__=='__main__':unittest.main()
