import unittest
import numpy as np
from centering_probe import center
class Centering(unittest.TestCase):
 def test_mean_uses_only_train(self):
  train=np.array([[1.,0.],[0.,1.]])
  a,m=center(train,np.vstack([train,[100.,100.]]));b,n=center(train,np.vstack([train,[-100.,-100.]]))
  np.testing.assert_array_equal(m,n);np.testing.assert_array_equal(a[:2],b[:2]);np.testing.assert_allclose(m,[.5,.5])
 def test_norm(self):
  t=np.array([[1.,0.],[0.,1.]]);z,m=center(t,t);np.testing.assert_allclose(np.linalg.norm(z,axis=1),[1,1])
 def test_zero_norm_refused(self):
  t=np.array([[1.,0.],[0.,1.]])
  with self.assertRaises(ValueError):center(t,np.array([[.5,.5]]))
if __name__=='__main__':unittest.main()
