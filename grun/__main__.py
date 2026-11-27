"""``python -m grun doctor ...`` and ``python -m grun vendor ...``"""
import sys

from . import doctor, vendor

if len(sys.argv) > 1 and sys.argv[1] == "vendor":
    sys.exit(vendor.main(sys.argv[2:]))
sys.exit(doctor.main())
