import unittest
from lola_uncertainty_calibration import calibrate_uncertainty

class UncertaintyCalibrationTests(unittest.TestCase):
    def test_unknowns_and_contradictions_raise_uncertainty(self):
        low=calibrate_uncertainty(evidence_count=4,independent_origins=3,unknowns=0,contradictions=0,failed_replays=0)
        high=calibrate_uncertainty(evidence_count=4,independent_origins=1,unknowns=2,contradictions=1,failed_replays=1)
        self.assertGreater(high.uncertainty,low.uncertainty)

    def test_calibration_is_bounded(self):
        r=calibrate_uncertainty(evidence_count=0,independent_origins=0,unknowns=100,contradictions=100,failed_replays=100)
        self.assertGreaterEqual(r.uncertainty,0.0)
        self.assertLessEqual(r.uncertainty,1.0)

    def test_calibration_does_not_authorize_execution(self):
        self.assertFalse(calibrate_uncertainty(evidence_count=10,independent_origins=10,unknowns=0,contradictions=0,failed_replays=0).execution_authority)

if __name__ == "__main__": unittest.main()
