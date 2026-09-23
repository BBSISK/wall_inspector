import unittest
from app import app, db, Wall

class TestStudiosAndAuth(unittest.TestCase):
    def setUp(self):
        self.client = app.test_client()

    def test_flashcards_studio(self):
        """Test Defect Flashcard Trainer page and API deck."""
        res = self.client.get('/cards')
        self.assertEqual(res.status_code, 200)
        self.assertIn(b'Masonry Pathology Flashcard', res.data)
        # Verify server hydration & zero empty image src
        self.assertNotIn(b'src=""', res.data)
        self.assertIn(b'ALL_CARDS =', res.data)

        # Verify archetype query filtering pre-hydrates matching cards
        res_ds = self.client.get('/cards?archetype=dry_stone')
        self.assertEqual(res_ds.status_code, 200)
        self.assertNotIn(b'src=""', res_ds.data)
        self.assertIn(b'Dry Stone', res_ds.data)

        # Deck API
        res_deck = self.client.get('/api/cards/deck')
        self.assertEqual(res_deck.status_code, 200)
        data = res_deck.get_json()
        self.assertTrue(data.get('success'))
        deck = data.get('deck', [])
        self.assertGreaterEqual(len(deck), 35)

        # Currency test & valid image test
        for card in deck:
            rate = card.get('euro_cost_rate', '')
            self.assertIn('€', rate, f"Card {card.get('id')} cost rate '{rate}' missing Euro symbol")
            img = card.get('image_url', '')
            self.assertTrue(img and len(img) > 0, f"Card {card.get('id')} has empty image URL")
            self.assertTrue(img.startswith('/static/img/walls/') or img.startswith('http'), f"Card {card.get('id')} invalid image: {img}")

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

    def test_ultratech_stone_specimens_and_catalog(self):
        """Verify authentic UltraTech stone masonry assets, database records, and 20 worked examples."""
        # 1. Verify worked examples catalog
        res = self.client.get('/examples')
        self.assertEqual(res.status_code, 200)
        self.assertIn(b'32 Student Assessment Worked Examples Catalog', res.data)
        self.assertIn(b'ultratech_stone_joints_01.jpg', res.data)
        self.assertIn(b'ultratech_stone_limerunoff_01.jpg', res.data)
        self.assertIn(b'ultratech_stone_bedding_01.jpg', res.data)
        self.assertIn(b'ultratech_stone_frost_01.jpg', res.data)
        self.assertIn(b'ultratech_cmu_blockwork_01.jpg', res.data)
        self.assertIn(b'heritage_cement_01.jpg', res.data)
        self.assertIn(b'heritage_chimney_01.jpg', res.data)
        self.assertIn(b'heritage_wigging_01.jpg', res.data)

        # 2. Verify UltraTech inspection pages
        res_wall = self.client.get('/inspect/ultratech-stone-continuous-joints')
        self.assertEqual(res_wall.status_code, 200)
        self.assertIn(b'Continuous Vertical Joint', res_wall.data)

        res_bedding = self.client.get('/inspect/ultratech-stone-improper-bedding')
        self.assertEqual(res_bedding.status_code, 200)
        self.assertIn(b'Face-Bedding', res_bedding.data)

        # 3. Verify total 32 standard catalog wall instances + 30 skill assessment instances
        from models import Wall
        with app.app_context():
            self.assertEqual(Wall.query.filter_by(is_skill_assessment=False).count(), 32)
            self.assertEqual(Wall.query.filter_by(is_skill_assessment=True).count(), 30)

        # 4. Verify Designing Buildings Wiki stonework inspection endpoints
        res_contour = self.client.get('/inspect/historic-sandstone-contour-scaling')
        self.assertEqual(res_contour.status_code, 200)
        self.assertIn(b'Contour Scaling', res_contour.data)

        res_gypsum = self.client.get('/inspect/sheltered-limestone-gypsum-cavitation')
        self.assertEqual(res_gypsum.status_code, 200)
        self.assertIn(b'Gypsum Crust', res_gypsum.data)

        # 5. Verify Heritage Brickwork Irish brick inspection endpoints
        res_cement = self.client.get('/inspect/dublin-georgian-cement-damage')
        self.assertEqual(res_cement.status_code, 200)
        self.assertIn(b'Portland Cement', res_cement.data)

        res_chimney = self.client.get('/inspect/victorian-dublin-chimney-decay')
        self.assertEqual(res_chimney.status_code, 200)
        self.assertIn(b'Chimney Stack', res_chimney.data)

        res_wigging = self.client.get('/inspect/georgian-terrace-irish-wigging')
        self.assertEqual(res_wigging.status_code, 200)
        self.assertIn(b'Wigging', res_wigging.data)

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

    def test_timed_examination_and_grading_pipeline(self):
        """Test Timed Student Examination console, submission, IoU grading, and scorecard."""
        # 1. Exam Console View
        res = self.client.get('/exam')
        self.assertEqual(res.status_code, 200)
        self.assertIn(b'Timed Masonry Examination Console', res.data)

        # 2. Start Exam Session API
        start_payload = {
            "student_name": "Test Candidate",
            "mode": "exam",
            "cohort_code": "GENERAL"
        }
        res_start = self.client.post('/api/exam/start', json=start_payload)
        self.assertEqual(res_start.status_code, 200)
        start_data = res_start.get_json()
        self.assertTrue(start_data.get('success'))
        exam_token = start_data.get('exam_token')
        self.assertTrue(bool(exam_token))
        walls = start_data.get('walls', [])
        self.assertEqual(len(walls), 5)

        # 3. Submit Wall Attempt
        first_wall = walls[0]
        submit_payload = {
            "exam_token": exam_token,
            "wall_id": first_wall['id'],
            "markers": [
                {
                    "x_min": 0.25,
                    "y_min": 0.30,
                    "x_max": 0.45,
                    "y_max": 0.60,
                    "category": "stepped_crack",
                    "severity": "critical",
                    "remedial_action": "helical_stitch"
                }
            ]
        }
        res_sub = self.client.post('/api/exam/submit-wall', json=submit_payload)
        self.assertEqual(res_sub.status_code, 200)
        self.assertTrue(res_sub.get_json().get('success'))

        # 4. Conclude Exam Session
        finish_payload = {
            "exam_token": exam_token,
            "student_name": "Test Candidate"
        }
        res_fin = self.client.post('/api/exam/finish', json=finish_payload)
        self.assertEqual(res_fin.status_code, 200)
        fin_data = res_fin.get_json()
        self.assertTrue(fin_data.get('success'))
        attempt_id = fin_data.get('attempt_id')
        self.assertTrue(bool(attempt_id))

        # 5. View Performance Scorecard
        res_card = self.client.get(f'/exam/result/{attempt_id}')
        self.assertEqual(res_card.status_code, 200)
        self.assertIn(b'Examination Performance Scorecard', res_card.data)
        self.assertIn(b'Test Candidate', res_card.data)
        self.assertIn(b'Spatial Calibration & Defect Overlap Analysis', res_card.data)

    def test_instructor_cohort_management_and_diagnostics(self):
        """Test instructor cohort dashboard, error heatmap, diagnostics API, and CSV export."""
        # 1. Cohorts Console
        res = self.client.get('/admin/cohorts')
        self.assertEqual(res.status_code, 200)
        self.assertIn(b'Instructor Cohort Management & Class Diagnostics', res.data)
        self.assertIn(b'Defect Blind Spot & Error Heatmap', res.data)

        # 2. Cohort Diagnostics API
        res_diag = self.client.get('/api/admin/cohorts/GENERAL/diagnostics')
        self.assertEqual(res_diag.status_code, 200)
        diag_data = res_diag.get_json()
        self.assertTrue(diag_data.get('success'))
        self.assertEqual(diag_data.get('cohort_code'), 'GENERAL')

        # 3. SIS Gradebook CSV Export
        res_csv = self.client.get('/api/admin/cohorts/GENERAL/csv')
        self.assertEqual(res_csv.status_code, 200)
        self.assertEqual(res_csv.mimetype, 'text/csv')
        csv_text = res_csv.data.decode('utf-8')
        self.assertIn('Candidate Name', csv_text)
        self.assertIn('Cohort PIN', csv_text)
        self.assertIn('CPD Hours', csv_text)

    def test_rics_survey_report_generator(self):
        """Test standalone RICS-format condition survey report with Euro BoQ."""
        res = self.client.get('/survey/report/ultratech-stone-continuous-joints')
        self.assertEqual(res.status_code, 200)
        self.assertIn(b'RICS Structural Masonry Condition Survey', res.data)
        self.assertIn(b'Condition Rating', res.data)
        self.assertIn(b'Itemized Conservation Bill of Quantities', res.data)
        self.assertIn('€'.encode('utf-8'), res.data)

    def test_ai_conservator_socratic_and_expert(self):
        """Test AI Conservator endpoint in both Socratic Hint and Clinical Specification modes."""
        # 1. Socratic Hint Mode
        res_hint = self.client.post('/api/ai/consult', json={
            "wall_slug": "ultratech-stone-continuous-joints",
            "mode": "hint",
            "box": {"x_min": 0.3, "y_min": 0.2, "x_max": 0.5, "y_max": 0.6, "category": "continuous_vertical_joint"}
        })
        self.assertEqual(res_hint.status_code, 200)
        hint_data = res_hint.get_json()
        self.assertTrue(hint_data.get('success'))
        self.assertTrue(bool(hint_data.get('hint')))

        # 2. Clinical Specification Mode
        res_spec = self.client.post('/api/ai/consult', json={
            "wall_slug": "ultratech-stone-continuous-joints",
            "mode": "expert",
            "box": {"x_min": 0.3, "y_min": 0.2, "x_max": 0.5, "y_max": 0.6, "category": "lime_washout"}
        })
        self.assertEqual(res_spec.status_code, 200)
        spec_data = res_spec.get_json()
        self.assertTrue(spec_data.get('success'))
        spec = spec_data.get('specification', {})
        self.assertIn('BS 8221', spec.get('standard', ''))
        self.assertIn('€', spec.get('estimated_rate_euro', ''))

    def test_embodied_carbon_sustainability_audit(self):
        """Test EN 15978 / PAS 2080 Embodied Carbon & Heritage Sustainability Audit in Survey Report."""
        res = self.client.get('/survey/report/ultratech-stone-continuous-joints')
        self.assertEqual(res.status_code, 200)
        self.assertIn(b'Embodied Carbon & Heritage Sustainability Audit', res.data)
        self.assertIn(b'EN 15978 / PAS 2080', res.data)
        self.assertIn(b'kg CO', res.data)
        self.assertIn(b'Demolition & Rebuild Carbon', res.data)
        self.assertIn(b'mature trees / yr', res.data)

    def test_advanced_pathology_tools(self):
        """Test Advanced Diagnostic Tools in inspection console: Cutaway, Thrust Statics, Tell-Tale, and Voice."""
        res = self.client.get('/inspect/ultratech-stone-continuous-joints')
        self.assertEqual(res.status_code, 200)
        # Verify toolbar trigger buttons
        self.assertIn(b'tool-cutaway', res.data)
        self.assertIn(b'tool-thrust', res.data)
        self.assertIn(b'tool-telltale', res.data)
        self.assertIn(b'btn-voice-dictate', res.data)
        # Verify modals and panels
        self.assertIn(b'cutaway-modal', res.data)
        self.assertIn(b'thrust-modal', res.data)
        self.assertIn(b'telltale-telemetry-panel', res.data)
        self.assertIn(b'voice-transcript-box', res.data)

    def test_upload_pipeline_and_connection_resilience(self):
        """Verify image upload pipeline creates valid Wall records with local fallback and non-null filename."""
        import io
        with self.client.session_transaction() as sess:
            sess['is_admin'] = True

        test_img = (io.BytesIO(b'fake_image_data_bytes_12345'), 'test_wall.jpg')
        res = self.client.post(
            '/mobile/admin/upload',
            data={
                'wall_image': test_img,
                'title': 'Unit Test Barry Wall',
                'description': 'Resilient upload test',
                'country': 'Ireland',
                'region': 'Dublin',
                'wall_type': 'brick_cavity',
                'structural_function': 'facade',
                'difficulty': 'beginner'
            },
            content_type='multipart/form-data'
        )
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertTrue(data['success'])
        self.assertEqual(data['wall']['title'], 'Unit Test Barry Wall')
        self.assertIsNotNone(data['wall']['image_filename'])
        self.assertTrue(data['wall']['image_filename'].endswith('.jpg'))

        # Verify record exists in database and cleanup
        with app.app_context():
            saved_wall = Wall.query.filter_by(title='Unit Test Barry Wall').first()
            self.assertIsNotNone(saved_wall)
            self.assertIsNotNone(saved_wall.image_filename)
            fn = saved_wall.image_filename
            db.session.delete(saved_wall)
            db.session.commit()
            import os
            fp = os.path.join(app.config["UPLOAD_FOLDER"], fn)
            if os.path.exists(fp):
                os.remove(fp)

    def test_skill_assessment_module(self):
        """Verify Student Skill Assessment Hub, interactive workstation, evaluation scoring, and photography guidelines admin."""
        # 1. Test Hub route
        res_hub = self.client.get('/skill-assessment')
        self.assertEqual(res_hub.status_code, 200)
        self.assertIn(b'Skill Assessment', res_hub.data)
        self.assertIn(b'Limestone Dry-Stone Wall', res_hub.data)
        self.assertIn(b'Coursed Sandstone Wall', res_hub.data)

        # 2. Test Student Workstation
        res_ws = self.client.get('/skill-assessment/skill-drystone-limestone-delamination')
        self.assertEqual(res_ws.status_code, 200)
        self.assertIn(b'Limestone Dry-Stone Wall: Core Voiding', res_ws.data)
        self.assertIn(b'Core Voids', res_ws.data)

        # 3. Test Student Pin Evaluation API with precise hit test
        eval_payload = {
            "student_name": "Test Candidate",
            "cohort_code": "SKILLS_TEST",
            "pins": [
                # Pin 1: Exact hit on hearting_washout (GT at 0.52, 0.38)
                {"x": 0.52, "y": 0.38, "category": "hearting_washout", "severity": "moderate"},
                # Pin 2: Location hit on lichen (GT at 0.34, 0.62) but category mismatch
                {"x": 0.35, "y": 0.61, "category": "mortar_erosion", "severity": "minor"},
                # Pin 3: False positive pin away from any defect
                {"x": 0.10, "y": 0.10, "category": "stepped_crack", "severity": "minor"}
            ]
        }
        res_eval = self.client.post(
            '/api/skill-assessment/evaluate/skill-drystone-limestone-delamination',
            json=eval_payload
        )
        self.assertEqual(res_eval.status_code, 200)
        eval_data = res_eval.get_json()
        self.assertTrue(eval_data['success'])
        self.assertEqual(eval_data['full_hits'], 1)
        self.assertEqual(eval_data['partial_hits'], 1)
        self.assertEqual(eval_data['false_positives'], 1)
        self.assertGreater(eval_data['score'], 0.0)
        self.assertIn('evaluated_pins', eval_data)
        self.assertIn('ground_truth', eval_data)
        self.assertEqual(len(eval_data['ground_truth']), 3)

        # 4. Test Instructor Admin and Photography Guidelines HUD
        with self.client.session_transaction() as sess:
            sess['is_admin'] = True

        res_admin = self.client.get('/skill-assessment/admin')
        self.assertEqual(res_admin.status_code, 200)
        self.assertIn(b'Photographic Capture Standards', res_admin.data)
        self.assertIn(b'Diffuse Overcast Daylight', res_admin.data)
        self.assertIn(b'Orthogonal Normal Angle', res_admin.data)

        # 5. Test Grader Canvas
        res_grader = self.client.get('/skill-assessment/admin/grade/skill-drystone-limestone-delamination')
        self.assertEqual(res_grader.status_code, 200)
        self.assertIn(b'Ground Truth Defect Grader', res_grader.data)
        self.assertIn(b'Specimen Dropdown', res_grader.data)

        # 6. Test Setting Specimen Defect Mode Palette (with Custom Title)
        custom_palette = [
            {"id": "delamination_spalling", "label": "Stone Delamination / Spalling"},
            {"id": "custom_frost_wedging_limestone", "label": "Frost Wedging of Bedded Limestone", "is_custom": True}
        ]
        res_modes = self.client.post(
            '/api/skill-assessment/modes/skill-drystone-limestone-delamination',
            json={"prioritized_modes": custom_palette}
        )
        self.assertEqual(res_modes.status_code, 200)
        modes_data = res_modes.get_json()
        self.assertTrue(modes_data['success'])
        self.assertEqual(len(modes_data['prioritized_modes']), 2)
        self.assertEqual(modes_data['prioritized_modes'][1]['id'], 'custom_frost_wedging_limestone')

        # 7. Test Student Workstation renders Prioritised Optgroup and Custom Mode
        res_student = self.client.get('/skill-assessment/skill-drystone-limestone-delamination')
        self.assertEqual(res_student.status_code, 200)
        self.assertIn(b'Specimen Relevant Defect Modes (Prioritised)', res_student.data)
        self.assertIn(b'Frost Wedging of Bedded Limestone', res_student.data)

        # 8. Test Student Evaluation with Custom Mode Pin (No hangs, proper status)
        eval_custom_payload = {
            "pins": [
                {
                    "id": "pin-c1",
                    "x": 0.42,
                    "y": 0.35,
                    "category": "custom_frost_wedging_limestone",
                    "severity": "critical"
                }
            ],
            "student_name": "Field Apprentice"
        }
        res_eval_custom = self.client.post(
            '/api/skill-assessment/evaluate/skill-drystone-limestone-delamination',
            json=eval_custom_payload
        )
        self.assertEqual(res_eval_custom.status_code, 200)
        eval_custom_data = res_eval_custom.get_json()
        self.assertTrue(eval_custom_data['success'])
        self.assertIn('evaluated_pins', eval_custom_data)
        self.assertIn('feedback', eval_custom_data)
        # Verify remedial_action is non-null string
        for fb in eval_custom_data['feedback']:
            self.assertIsNotNone(fb.get('remedial_action'))


if __name__ == '__main__':
    unittest.main()



