import re
import shutil
from collections import namedtuple
from concurrent.futures import ThreadPoolExecutor
from os import environ, makedirs
from os.path import exists, expanduser, join
from pathlib import Path

import requests
from tqdm.auto import tqdm
from yaml import load
from multiprocessing import cpu_count

PERMANENT_DOI = "8039909"

RemoteFileMetadata = namedtuple("RemoteFileMetadata", ["filename", "url", "checksum"])

pbar = {}

def get_models_home(models_home=None) -> str:
    if models_home is None:
        models_home = environ.get("NMMA_MODELS", join("~", "nmma_models"))
    models_home = expanduser(models_home)
    makedirs(models_home, exist_ok=True)
    return models_home

def clear_data_home(models_home=None):
    models_home = get_models_home(models_home)
    shutil.rmtree(models_home)

def get_latest_zenodo_doi(permanent_doi):
    r = requests.get(f"https://zenodo.org/record/{permanent_doi}", allow_redirects=True)
    data = r.text.split("10.5281/zenodo.")[1]
    doi = re.findall(r"^\d+", data)[0]
    return doi

def download(file_info):
    url, filepath = file_info
    resp = requests.get(url, stream=True)
    total = int(resp.headers.get('content-length', 0))
    chunk_size = 1024
    with open(filepath, 'wb') as f, tqdm(total=total, unit='iB', unit_scale=True, unit_divisor=1024, desc=f"{str(filepath).split('/')[-1]}") as pbar:
        for chunk in resp.iter_content(chunk_size=chunk_size):
            size = f.write(chunk)
            pbar.update(size)

    return filepath

def download_models_list(doi=None):
    #first we load the models list from zenodo
    models_home = get_models_home()
    if not exists(models_home):
        makedirs(models_home)
    r = requests.get(f"https://zenodo.org/record/{doi}/files/models.yaml", allow_redirects=True)
    with open(Path(models_home, "models.yaml"), "wb") as f:
        f.write(r.content)

def load_models_list(doi=None):
    # if models.yaml doesn't exist, download it
    models_home = get_models_home()
    if not exists(Path(models_home, "models.yaml")):
        download_models_list(doi=doi)
    try:
        from yaml import CLoader as Loader
    except ImportError:
        from yaml import Loader
    with open(Path(models_home, "models.yaml"), "r") as f:
        models = load(f, Loader=Loader)
    return models

DOI = get_latest_zenodo_doi(PERMANENT_DOI)
MODELS = load_models_list(DOI)

def get_model(
    models_home=None,
    model_name=None,
    filters=[],
    download_if_missing=True,
):
    base_url = f"https://zenodo.org/record/{DOI}/files"
    if model_name is None:
        raise ValueError("model_name must be specified, got None")
    if model_name not in MODELS:
        #raise ValueError("model_name must be one of %s, got %s" % (MODELS.keys(), model_name))
        return [] #TODO: upload all the models on zenodo so we can throw an error here instead of returning an empty list
    model_info = MODELS[model_name]

    models_home = get_models_home(models_home)
    if not exists(models_home):
        makedirs(models_home)
    if not exists(Path(models_home, model_name)):
        makedirs(Path(models_home, model_name))
    if not exists(Path(models_home, model_name, 'filters')):
        makedirs(Path(models_home, model_name, 'filters'))
    if filters in [[], None, ''] and 'filters' in model_info:
        filters = model_info['filters']

    filepaths = [Path(models_home, f"{model_name}.pkl")] + [Path(models_home, model_name, f"{f}.pkl") for f in filters]
    urls = [f"{base_url}/{model_name}.pkl?download=1"] + [f"{base_url}/{model_name}_{f}.pkl?download=1" for f in filters]

    missing = [(u,f) for u, f in zip(urls, filepaths) if not f.exists()]
    if len(missing) > 0:
        if not download_if_missing:
            raise OSError("Data not found and `download_if_missing` is False")
        
        print(f"downloading {len(missing)} files for model {model_name}:")
        with ThreadPoolExecutor(max_workers=min(len(missing), max(cpu_count(), 8))) as executor:
            executor.map(download, missing)
        
    # return the paths to the files
    return [str(f) for f in filepaths]

if __name__ == "__main__":
    #TODO: remove, this is for testing only
    print(get_model("Bu2019nsbh", filters=["sdssu"]))