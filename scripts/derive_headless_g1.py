"""Reproduce the licensed, visual-mesh-only G1 derivative without network or execution."""
from __future__ import annotations
import hashlib
import json
from pathlib import Path
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]


def derive(output: Path) -> dict:
    source = ROOT / 'third_party' / 'unitree_g1'
    manifest = json.loads((source / 'sources.json').read_text())
    aliases = {'upstream_g1_mjx.xml': 'g1_mjx.xml', 'upstream_scene_mjx.xml': 'scene_mjx.xml', 'LICENSE': 'LICENSE'}
    for entry in manifest['sources']:
        data = (source / aliases[entry['file']]).read_bytes()
        if hashlib.sha256(data).hexdigest() != entry['sha256']:
            raise ValueError('upstream source hash mismatch')
        if hashlib.sha1(b'blob ' + str(len(data)).encode() + b'\0' + data).hexdigest() != entry['git_blob_sha']:
            raise ValueError('upstream Git blob hash mismatch')
    robot = ET.parse(source / 'g1_mjx.xml').getroot()
    scene = ET.parse(source / 'scene_mjx.xml').getroot()
    if not all(body.find('inertial') is not None for body in robot.findall('.//body')):
        raise ValueError('cannot remove visuals when body inertia is implicit')
    visual = robot.find(".//default[@class='visual']")
    if visual is None or visual.find('geom').get('density') != '0':
        raise ValueError('unexpected visual definition')
    removed = 0
    for parent in robot.iter():
        for child in list(parent):
            if child.tag == 'geom' and child.get('class') == 'visual':
                parent.remove(child)
                removed += 1
            if child.tag == 'default' and child.get('class') == 'visual':
                parent.remove(child)
    asset = robot.find('asset')
    meshes = asset.findall('mesh')
    for mesh in meshes:
        asset.remove(mesh)
    robot.find('compiler').attrib.pop('meshdir', None)
    if any('mesh' in item.attrib or item.get('type') == 'mesh' for item in robot.iter()):
        raise ValueError('unexpected remaining mesh reference')
    scene.find('include').set('file', 'unitree_g1_headless.xml')
    output.mkdir(parents=True, exist_ok=True)
    files = {}
    for name, xml in [('unitree_g1_headless.xml', robot), ('unitree_g1_scene.xml', scene)]:
        ET.indent(xml)
        data = ('<!-- Modified visual-mesh-free derivative. See unitree_g1_NOTICE.txt and unitree_g1_LICENSE.txt. -->\n'
                + ET.tostring(xml, encoding='unicode') + '\n').encode()
        (output / name).write_bytes(data)
        files[name] = hashlib.sha256(data).hexdigest()
    (output / 'unitree_g1_LICENSE.txt').write_bytes((source / 'LICENSE').read_bytes())
    result = {'source_repository': 'https://github.com/google-deepmind/mujoco_menagerie',
              'source_commit': manifest['commit'], 'source_files': manifest['sources'],
              'modified': True, 'removed_zero_density_visual_geoms': removed,
              'removed_visual_mesh_assets': len(meshes), 'preserved_explicit_inertias': len(robot.findall('.//inertial')),
              'preserved_contact_pairs': len(scene.findall('.//pair')), 'runtime_sha256': files}
    (output / 'unitree_g1_source.json').write_text(json.dumps(result, indent=2) + '\n')
    return result


if __name__ == '__main__':
    print(json.dumps(derive(ROOT / 'src' / 'jace' / 'data'), indent=2))
