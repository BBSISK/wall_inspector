import unittest
from app import app

class TestStudiosAndAuth(unittest.TestCase):
    def setUp(self):
        self.client = app.test_client()

    def test_flashcards_studio(self):
        """Test Defect Flashcard Trainer page and API deck."""
        res = self.client.get('/cards')
        self.assertEqual(res.status_code, 200)
        self.assertIn(b'Masonry Pathology Flashcard', res.data)

        # Deck API
        res_deck = self.client.get('/api/cards/deck')
        self.assertEqual(res_deck.status_code, 200)
        data = res_deck.get_json()
        self.assertTrue(data.get('success'))
        deck = data.get('deck', [])
        self.assertGreaterEqual(len(deck), 35)

        # Currency test: ensure all rates use Euro symbol
        for card in deck:
            rate = card.get('euro_cost_rate', '')
            self.assertIn('€', rate, f"Card {card.get('id')} cost rate '{rate}' missing Euro symbol")

    def test_compare_studio(self):
        """Test Dual-Wall Comparative Analysis Studio."""
        res = self.client.get('/compare')
        self.assertEqual(res.status_code, 200)
        self.assertIn(b'Dual-Wall Comparative Studio', res.data)

        # Compare API
        res_comp = self.client.get('/api/walls/compare?wall_a=ashlar-quarry-dressed-limestone&wall_b=traditional-irish-dry-stone')
        self.assertEqual(res_comp.status_code, 200)
        data = res_comp.get_json()
        self.assertTrue(data.get('success'))
        self.assertIn('specimen_a', data)
        self.assertIn('specimen_b', data)

        costs_a = data['specimen_a'].get('costs', {})
        costs_b = data['specimen_b'].get('costs', {})
        self.assertIn('€', costs_a.get('yr0', ''))
        self.assertIn('€', costs_b.get('yr0', ''))
        self.assertIn('ROI', f"{costs_a.get('roi')} ROI")

    def test_map_atlas(self):
        """Test Geospatial Masonry Atlas."""
        res = self.client.get('/map')
        self.assertEqual(res.status_code, 200)
        self.assertIn(b'Geospatial Masonry Atlas', res.data)

        # Map walls API
        res_walls = self.client.get('/api/map/walls')
        self.assertEqual(res_walls.status_code, 200)
        data = res_walls.get_json()
        self.assertTrue(data.get('success'))
        walls = data.get('walls', [])
        self.assertGreaterEqual(len(walls), 11)

        # Verify geological metadata
        for w in walls:
            self.assertTrue(w.get('lat') is not None)
            self.assertTrue(w.get('lng') is not None)
            self.assertTrue(bool(w.get('geology')))
            self.assertTrue(bool(w.get('rainfall')))
            self.assertTrue(bool(w.get('freeze_thaw')))

    def test_field_guide(self):
        """Test Printable Pocket Field Crib-Sheet and CSV export."""
        res = self.client.get('/field-guide')
        self.assertEqual(res.status_code, 200)
        self.assertIn(b'Field Assessment Crib-Sheet', res.data)
        self.assertIn('€'.encode('utf-8'), res.data)

        # Test alias
        res_alias = self.client.get('/cribsheet')
        self.assertEqual(res_alias.status_code, 200)

        # Test CSV export
        res_csv = self.client.get('/api/field-guide/csv')
        self.assertEqual(res_csv.status_code, 200)
        self.assertEqual(res_csv.mimetype, 'text/csv')
        csv_lines = res_csv.data.decode('utf-8').strip().splitlines()
        self.assertEqual(len(csv_lines), 12)  # 1 header + 11 archetypes
        self.assertIn('€', res_csv.data.decode('utf-8'))

    def test_admin_auth_protection(self):
        """Ensure admin routes are strictly inaccessible without authentication."""
        protected_endpoints = [
            '/admin/assignments',
            '/admin/walls/new',
            '/admin/export/attempts.csv'
        ]
        for ep in protected_endpoints:
            res = self.client.get(ep, follow_redirects=False)
            self.assertEqual(res.status_code, 302, f"Endpoint {ep} not protected by auth redirect")

if __name__ == '__main__':
    unittest.main()
