from __future__ import annotations

import re
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path

from .config import Config

TOP_FEEDS = {
    "parcels": "https://www.catastro.hacienda.gob.es/INSPIRE/CadastralParcels/ES.SDGC.CP.atom.xml",
    "addresses": "https://www.catastro.hacienda.gob.es/INSPIRE/Addresses/ES.SDGC.AD.atom.xml",
    "buildings": "https://www.catastro.hacienda.gob.es/INSPIRE/buildings/ES.SDGC.BU.atom.xml",
}
CODE_PATTERN = re.compile(r"\.([0-9]{5})\.zip$", re.IGNORECASE)


def local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def clean_url(url: str) -> str:
    url = url.replace(
        "http://www.catastro.hacienda.gob.es",
        "https://www.catastro.hacienda.gob.es",
    )
    parts = urllib.parse.urlsplit(url)
    path = urllib.parse.quote(re.sub(r"\s+", " ", parts.path), safe="/%:@")
    query = urllib.parse.quote(parts.query, safe="=&%:+,/?")
    return urllib.parse.urlunsplit((parts.scheme, parts.netloc, path, query, parts.fragment))


@dataclass(frozen=True)
class DownloadTask:
    collection: str
    province_code: str
    municipality_code: str
    municipality_name: str
    url: str
    path: Path

    @property
    def task_id(self) -> str:
        return f"{self.collection}:{self.municipality_code}"

    def public_dict(self, raw_dir: Path) -> dict[str, str]:
        return {
            "collection": self.collection,
            "province_code": self.province_code,
            "municipality_code": self.municipality_code,
            "municipality_name": self.municipality_name,
            "url": self.url,
            "file": self.path.relative_to(raw_dir).as_posix(),
        }


def fetch_xml(url: str, path: Path, config: Config) -> bytes:
    if path.exists():
        content = path.read_bytes()
        try:
            ET.fromstring(content)
            return content
        except ET.ParseError:
            path.unlink()
    request = urllib.request.Request(clean_url(url), headers={"User-Agent": config.user_agent})
    with urllib.request.urlopen(request, timeout=config.timeout_seconds) as response:
        content = response.read()
    ET.fromstring(content)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_bytes(content)
    temporary.replace(path)
    time.sleep(config.request_delay_seconds)
    return content


def atom_entries(content: bytes) -> list[tuple[str, list[dict[str, str]]]]:
    root = ET.fromstring(content)
    result: list[tuple[str, list[dict[str, str]]]] = []
    for entry in (item for item in root.iter() if local_name(item.tag) == "entry"):
        title = next(
            ((item.text or "").strip() for item in entry if local_name(item.tag) == "title"),
            "",
        )
        links = [
            {key: value for key, value in item.attrib.items() if key in {"href", "type", "rel"}}
            for item in entry
            if local_name(item.tag) == "link" and item.attrib.get("href")
        ]
        result.append((title, links))
    return result


def discover(config: Config) -> list[DownloadTask]:
    tasks: list[DownloadTask] = []
    catalog_dir = config.raw_dir / "catalogs"
    for collection in config.collections:
        top_url = TOP_FEEDS[collection]
        top_content = fetch_xml(top_url, catalog_dir / f"{collection}.atom.xml", config)
        provincial_links = [
            clean_url(link["href"])
            for _, links in atom_entries(top_content)
            for link in links
            if link.get("type") == "application/atom+xml"
            and "catastro.hacienda.gob.es" in link.get("href", "")
        ]
        for provincial_url in provincial_links:
            filename = Path(urllib.parse.urlparse(provincial_url).path).name
            province_match = re.search(r"_([0-9]{2})\.xml$", filename, re.IGNORECASE)
            if not province_match:
                continue
            province_code = province_match.group(1)
            content = fetch_xml(
                provincial_url,
                catalog_dir / collection / f"{province_code}.atom.xml",
                config,
            )
            for title, links in atom_entries(content):
                archive_url = next(
                    (
                        clean_url(link["href"])
                        for link in links
                        if link.get("href", "").lower().endswith(".zip")
                    ),
                    None,
                )
                if not archive_url:
                    continue
                match = CODE_PATTERN.search(archive_url)
                if not match:
                    continue
                municipality_code = match.group(1)
                name = re.sub(r"^.*?[- ]", "", title).strip()
                name = re.sub(r"\s+(addresses|buildings|Cadastral Parcels)$", "", name, flags=re.IGNORECASE)
                name = name or municipality_code
                target = config.raw_dir / "archives" / collection / province_code / Path(
                    urllib.parse.urlparse(archive_url).path
                ).name
                tasks.append(
                    DownloadTask(
                        collection,
                        province_code,
                        municipality_code,
                        name,
                        archive_url,
                        target,
                    )
                )
    requested = set(config.municipality_codes) if config.municipality_codes else None
    codes = sorted(
        {
            task.municipality_code
            for task in tasks
            if requested is None or task.municipality_code in requested
        }
    )
    if requested:
        missing = sorted(requested - set(codes))
        if missing:
            raise ValueError(f"Municipality codes not found: {', '.join(missing)}")
    if config.max_municipalities is not None:
        codes = codes[: config.max_municipalities]
    selected = set(codes)
    return sorted(
        (task for task in tasks if task.municipality_code in selected),
        key=lambda task: (task.municipality_code, task.collection),
    )
