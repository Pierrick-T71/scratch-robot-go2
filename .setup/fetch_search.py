import io
import tarfile
import urllib.request

URL = "https://files.pythonhosted.org/packages/source/c/cyclonedds/cyclonedds-0.10.2.tar.gz"
data = urllib.request.urlopen(URL, timeout=90).read()
tar = tarfile.open(fileobj=io.BytesIO(data))
for name in tar.getnames():
    if "buildhelp/cyclone_search" in name:
        tar.extract(name, "/tmp", filter="data")
        print("extrait:", name)