# iCoDer Backend

# Install before importing any API/service module. Optional dependency chains
# can otherwise reach known-crashing Windows native extensions before the
# call-site MedCodER/Memory safety checks have a chance to run.
from app.native_import_guard import install_known_unsafe_native_import_guard


install_known_unsafe_native_import_guard()
