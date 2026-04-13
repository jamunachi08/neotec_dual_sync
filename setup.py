from setuptools import setup, find_packages

setup(
    name="neotec_dual_sync",
    version="1.1.0",
    description="Settings-driven dual instance synchronization for Frappe",
    author="Neotec",
    author_email="support@neotec.example",
    packages=find_packages(),
    include_package_data=True,
    zip_safe=False,
)
