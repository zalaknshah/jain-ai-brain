"""Static recipe regressions, not Docker build/network/stop qualification."""

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ASSETS = {
    'canonical.json', 'articulated_scene.xml', 'slider_scene.xml',
    'source_review.js', 'unitree_g1_LICENSE.txt', 'unitree_g1_NOTICE.txt',
    'unitree_g1_headless.xml', 'unitree_g1_scene.xml', 'unitree_g1_source.json',
}


class ContainerRecipeTests(unittest.TestCase):
    def rules(self):
        return [line.strip() for line in (ROOT / '.dockerignore').read_text().splitlines()
                if line.strip() and not line.lstrip().startswith('#')]

    def test_context_uses_small_explicit_allowlist(self):
        # Assert the complete narrow rule grammar rather than implementing a
        # general Docker ignore parser whose semantics might differ from Docker.
        expected = {
            '!Dockerfile', '!pyproject.toml', '!README.md', '!LICENSE',
            '!src/jace_study_query.py',
            '!src/jace/_fresh_study/__init__.py',
            '!src/jace/_fresh_study/consumer.py',
            '!src/jace/_fresh_study/preparation.py',
            *('!' + path.relative_to(ROOT).as_posix()
              for path in (ROOT / 'src/jace').glob('*.py')),
            *('!src/jace/data/' + name for name in ASSETS),
        }
        rules = self.rules()
        self.assertEqual(rules[0], '**')
        self.assertEqual(set(rules[1:]), expected)
        self.assertEqual(len(rules[1:]), len(expected))
        for rule in rules[1:]:
            self.assertNotRegex(rule, r'[*?\[\]]')
            self.assertTrue((ROOT / rule[1:]).is_file())
            self.assertFalse(rule.endswith('/'))

    def test_allowlist_covers_required_package_assets(self):
        for name in ASSETS:
            with self.subTest(asset=name):
                self.assertTrue((ROOT / 'src/jace/data' / name).is_file())
        # New package assets need an explicit context review. Ignore only local
        # generated caches, which are not package assets.
        actual = {path.name for path in (ROOT / 'src/jace/data').iterdir()
                  if path.is_file() and not path.name.startswith('.')}
        self.assertEqual(actual, ASSETS)

    def test_synthetic_private_and_generated_names_are_not_allowed(self):
        allowed = {rule[1:] for rule in self.rules()[1:]}

        for name in (
            '.env', '.env.local', '.git/config', 'data/jace.sqlite3',
            'data/jace.sqlite3-wal', 'data/canonical.json', 'data/private.txt',
            'research/original.txt', 'training/fixtures/train.jsonl',
            'build/lib/jace/private.json', 'dist/jace.whl',
            'src/jace.egg-info/SOURCES.txt', 'src/jace/__pycache__/cli.pyc',
            'src/jace/.env', 'src/jace/private.sqlite3',
            'src/jace/_fresh_study/private.txt',
            'src/jace/_fresh_study/records.jsonl',
            'src/jace/_fresh_study/original.xml',
            'src/jace/data/private.json', 'src/jace/data/canonical.json.bak',
            'web/index.html', 'tests/test_jace.py',
        ):
            with self.subTest(synthetic_name=name):
                self.assertNotIn(name, allowed)
        for name in ('src/jace/cli.py', 'src/jace_study_query.py', 'src/jace/data/canonical.json', 'pyproject.toml'):
            self.assertIn(name, allowed)

    def test_image_does_not_copy_runtime_data_or_entire_checkout(self):
        copies = [line for line in (ROOT / 'Dockerfile').read_text().splitlines()
                  if line.startswith('COPY ')]
        self.assertEqual(copies, ['COPY pyproject.toml README.md LICENSE ./', 'COPY src ./src'])

    def test_compose_publishes_host_loopback_and_preserves_runtime_volume(self):
        recipe = (ROOT / 'docker-compose.yml').read_text()
        self.assertIn('      - "127.0.0.1:8787:8787"', recipe)
        self.assertNotIn('      - "8787:8787"', recipe)
        self.assertIn('      JACE_HOST: 0.0.0.0', recipe)
        self.assertIn('      JACE_DB_PATH: /app/data/jace.sqlite3', recipe)
        self.assertIn('      - jace-data:/app/data', recipe)


if __name__ == '__main__':
    unittest.main()
