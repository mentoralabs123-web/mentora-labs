"""Task 5B admin dashboard and management route tests (SQLite)."""
import base64, io, os, re, sys, tempfile, types, unittest
from werkzeug.security import generate_password_hash
ROOT=os.path.dirname(os.path.dirname(os.path.abspath(__file__))); sys.path.insert(0,ROOT)
try:
    import psycopg  # noqa
except ImportError:
    stub=types.ModuleType('psycopg'); stub.rows=types.ModuleType('psycopg.rows'); stub.rows.dict_row=None
    sys.modules['psycopg'],sys.modules['psycopg.rows']=stub,stub.rows
import app as site
import project_service as svc

class AdminManagementTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(); self.old=(site.DB_PATH,site.ADMIN_USER,site._ADMIN_PASSWORD_HASH,site.app.secret_key,site.ADMIN_UPLOAD_DIR)
        site.DB_PATH=os.path.join(self.tmp.name,'db.sqlite'); site.ADMIN_USER='admin-test'
        site._ADMIN_PASSWORD_HASH=generate_password_hash('strong-test-password'); site.ADMIN_UPLOAD_DIR=os.path.join(self.tmp.name,'uploads','projects')
        site.app.secret_key='test-secret-key-that-is-long-enough-123456789'; site.app.config.update(TESTING=True,SESSION_COOKIE_SECURE=False)
        site.init_db(); self.client=site.app.test_client()
    def tearDown(self):
        site.DB_PATH,site.ADMIN_USER,site._ADMIN_PASSWORD_HASH,site.app.secret_key,site.ADMIN_UPLOAD_DIR=self.old
        self.tmp.cleanup()
    def csrf(self):
        html=self.client.get('/admin').get_data(as_text=True)
        return re.search(r'name="csrf_token" value="([^"]+)"',html).group(1)
    def login(self):
        token=self.csrf(); r=self.client.post('/admin',data={'username':'admin-test','password':'strong-test-password','csrf_token':token})
        self.assertEqual(r.status_code,303)
        with self.client.session_transaction() as sess: return sess['admin_csrf']
    def test_dashboard_live_counts_and_routes_protected(self):
        self.assertEqual(self.client.get('/admin/projects').status_code,302)
        self.login(); html=self.client.get('/admin/dashboard').get_data(as_text=True)
        self.assertIn('Total projects',html); self.assertIn('Student orders',html); self.assertIn('Business enquiries',html)
    def test_project_create_edit_publish_and_delete(self):
        token=self.login()
        import sqlite3
        conn=sqlite3.connect(site.DB_PATH); conn.row_factory=sqlite3.Row
        cats=svc.get_categories(conn,only_used=False,published_only=False)
        self.assertTrue(cats)
        data={'csrf_token':token,'title':'Admin CRUD Demo','short_description':'Short summary','description':'Detailed text',
              'technologies':'Flask, Python','categories':[cats[0]['slug']],'project_url':'https://example.com',
              'featured':'1','published':'1','display_order':'2'}
        r=self.client.post('/admin/projects/new',data=data,follow_redirects=False)
        self.assertEqual(r.status_code,303)
        db=conn; project=svc.get_project_by_slug(db,'admin-crud-demo'); self.assertIsNotNone(project)
        self.assertTrue(project['featured']); self.assertTrue(project['published']); self.assertEqual(project['technologies'],['Flask','Python'])
        r=self.client.post(f"/admin/projects/{project['id']}/edit",data={'csrf_token':token,'title':'Admin CRUD Demo Updated','published':'0','featured':'0','technologies':'Django'})
        self.assertEqual(r.status_code,303); updated=svc.get_project_by_id(db,project['id'])
        self.assertEqual(updated['title'],'Admin CRUD Demo Updated'); self.assertFalse(updated['published']); self.assertFalse(updated['featured'])
        r=self.client.post(f"/admin/projects/{project['id']}/delete",data={'csrf_token':token})
        self.assertEqual(r.status_code,303); self.assertIsNone(svc.get_project_by_id(db,project['id'])); db.close()
    def test_image_upload_validates_signature_and_size(self):
        token=self.login()
        bad={'csrf_token':token,'title':'Bad Image','image_file':(io.BytesIO(b'not a png'),'x.png')}
        r=self.client.post('/admin/projects/new',data=bad,content_type='multipart/form-data')
        self.assertEqual(r.status_code,200); self.assertIn('does not match',r.get_data(as_text=True))
    def test_valid_image_upload_is_persisted_and_removed_after_project_delete(self):
        token=self.login()
        png=base64.b64decode('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+/p9sAAAAASUVORK5CYII=')
        r=self.client.post('/admin/projects/new',data={'csrf_token':token,'title':'Thumbnail Test','published':'1',
            'image_file':(io.BytesIO(png),'thumb.png')},content_type='multipart/form-data')
        self.assertEqual(r.status_code,303)
        import sqlite3
        db=sqlite3.connect(site.DB_PATH); db.row_factory=sqlite3.Row
        project=svc.get_project_by_slug(db,'thumbnail-test'); self.assertIsNotNone(project)
        path=project['image']; self.assertTrue(path.startswith('uploads/projects/'))
        full=os.path.join(site.ADMIN_UPLOAD_DIR,os.path.basename(path)); self.assertTrue(os.path.isfile(full))
        with self.client.session_transaction() as sess: csrf=sess['admin_csrf']
        self.client.post(f"/admin/projects/{project['id']}/delete",data={'csrf_token':csrf})
        self.assertFalse(os.path.exists(full)); db.close()
    def test_order_and_enquiry_read_views(self):
        self.login()
        import sqlite3
        db=sqlite3.connect(site.DB_PATH)
        db.execute('INSERT INTO orders(name,contact,track,message,created_at) VALUES(?,?,?,?,?)',('Student','s@example.com','Python','hello','2026-01-01T00:00:00Z'))
        db.execute('INSERT INTO business_enquiries(name,service,project_description,status,created_at,updated_at) VALUES(?,?,?,?,?,?)',('Business','website-development','Need a site','New','2026-01-02T00:00:00Z','2026-01-02T00:00:00Z')); db.commit(); db.close()
        self.assertIn('Student',self.client.get('/admin/orders?q=Student').get_data(as_text=True))
        self.assertIn('Business',self.client.get('/admin/enquiries?q=Business').get_data(as_text=True))
        self.assertEqual(self.client.get('/admin/orders/1').status_code,200)
    def test_business_enquiry_uses_existing_status_vocabulary(self):
        token=self.login()
        import sqlite3
        db=sqlite3.connect(site.DB_PATH)
        db.execute('INSERT INTO business_enquiries(name,service,project_description,status,created_at,updated_at) VALUES(?,?,?,?,?,?)',
                   ('Status Test','website-development','Need a website','New','2026-01-02T00:00:00Z','2026-01-02T00:00:00Z'))
        db.commit(); db.close()
        for status in ('Contacted','In Progress','Completed','Closed'):
            response=self.client.post('/admin/enquiries/1',data={'csrf_token':token,'status':status,'admin_notes':'QA update'})
            self.assertEqual(response.status_code,303,status)
            db=sqlite3.connect(site.DB_PATH)
            saved=db.execute('SELECT status,admin_notes FROM business_enquiries WHERE id=1').fetchone()
            db.close()
            self.assertEqual(saved,(status,'QA update'))

    def test_csrf_and_logout(self):
        token=self.login(); r=self.client.post('/admin/projects/new',data={'title':'no token'})
        self.assertEqual(r.status_code,400)
        self.assertEqual(self.client.post('/admin/logout',data={'csrf_token':token}).status_code,303)
        self.assertEqual(self.client.get('/admin/dashboard').status_code,302)

if __name__=='__main__': unittest.main()
