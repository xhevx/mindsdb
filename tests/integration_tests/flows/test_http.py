from pathlib import Path
import json

import requests
import pandas as pd
import pytest

from mindsdb.api.executor.data_types.response_type import RESPONSE_TYPE
from .conftest import make_test_csv
from tests.utils.http_test_helpers import HTTPHelperMixin


# used by mindsdb_app fixture in conftest
OVERRIDE_CONFIG = {
    'tasks': {'disable': True},
    'jobs': {'disable': True}
}
# used by (required for) mindsdb_app fixture in conftest
API_LIST = ["http"]

HTTP_API_ROOT = 'http://127.0.0.1:47334/api'

USE_GUI = True


@pytest.mark.usefixtures('mindsdb_app', 'postgres_db', 'mysql_db', 'maria_db')
class TestHTTP(HTTPHelperMixin):
    @staticmethod
    def get_files_list():
        response = requests.request('GET', f'{HTTP_API_ROOT}/files/')
        assert response.status_code == 200
        response_data = response.json()
        assert isinstance(response_data, list)
        return response_data

    @classmethod
    def setup_class(cls):
        cls._sql_via_http_context = {}

    def show_databases(self):
        resp = self.sql_via_http('show databases', RESPONSE_TYPE.TABLE)
        return [x[0] for x in resp['data']]

    @pytest.mark.parametrize("util_uri", ["util/ping", "util/ping_native", "config/vars"])
    def test_utils(self, util_uri):
        """
        Call utilities ping endpoint
        THEN check the response is success
        """

        path = f"{HTTP_API_ROOT}/{util_uri}"
        response = requests.get(path)
        assert response.status_code == 200

    def test_auth(self):
        session = requests.Session()

        response = session.get(f'{HTTP_API_ROOT}/status')
        assert response.status_code == 200
        assert response.json()['auth']['http_auth_enabled'] is False

        response = session.get(f'{HTTP_API_ROOT}/config/')
        assert response.status_code == 200
        assert response.json()['auth']['http_auth_enabled'] is False

        response = session.get(f'{HTTP_API_ROOT}/tree/')
        assert response.status_code == 200

        response = session.put(f'{HTTP_API_ROOT}/config/', json={
            'http_auth_enabled': True,
            'username': '',
            'password': ''
        })
        assert response.status_code == 400

        response = session.put(f'{HTTP_API_ROOT}/config/', json={
            'auth': {
                'http_auth_enabled': True,
                'username': 'mindsdb',
                'password': 'mindsdb'
            }
        })
        assert response.status_code == 200

        response = session.get(f'{HTTP_API_ROOT}/status')
        assert response.status_code == 200
        assert response.json()['auth']['http_auth_enabled'] is True

        response = session.get(f'{HTTP_API_ROOT}/tree/')
        assert response.status_code == 403

        response = session.post(f'{HTTP_API_ROOT}/login', json={
            'username': 'mindsdb',
            'password': 'mindsdb'
        })
        assert response.status_code == 200

        response = session.get(f'{HTTP_API_ROOT}/tree/')
        assert response.status_code == 200

        response = session.post(f'{HTTP_API_ROOT}/logout')
        assert response.status_code == 200

        response = session.get(f'{HTTP_API_ROOT}/tree/')
        assert response.status_code == 403

        response = session.post(f'{HTTP_API_ROOT}/login', json={
            'username': 'mindsdb',
            'password': 'mindsdb'
        })
        assert response.status_code == 200

        response = session.put(f'{HTTP_API_ROOT}/config/', json={
            'auth': {
                'http_auth_enabled': False,
                'username': 'mindsdb',
                'password': 'mindsdb'
            }
        })

        response = session.get(f'{HTTP_API_ROOT}/status')
        assert response.status_code == 200
        assert response.json()['auth']['http_auth_enabled'] is False

    def test_gui_is_served(self):
        """
        GUI downloaded and available
        """
        response = requests.get('http://localhost:47334/')
        assert response.status_code == 200
        assert response.content.decode().find('<head>') > 0

    def test_files(self):
        ''' sql-via-http:
            upload file
            delete file
            upload file again
        '''
        files_list = self.get_files_list()
        assert len(files_list) == 0

        if Path('train.csv').is_file() is False:
            resp = requests.get('https://raw.githubusercontent.com/mindsdb/mindsdb-examples/master/classics/home_rentals/dataset/train.csv')
            with open('tests/train.csv', 'wb') as f:
                f.write(resp.content)

        file_path = Path('tests/train.csv')
        df = pd.read_csv(file_path)
        test_csv_path = make_test_csv('test_home_rentals', df.head(50))
        small_test_csv_path = make_test_csv('small_test_home_rentals', df.head(5))

        with open(test_csv_path) as td:
            files = {
                'file': ('test_data.csv', td, 'text/csv'),
                'original_file_name': (None, 'super_test_data.csv')  # optional
            }

            response = requests.request('PUT', f'{HTTP_API_ROOT}/files/test_file', files=files, json=None, params=None, data=None)
            assert response.status_code == 200

        files_list = self.get_files_list()
        assert files_list[0]['name'] == 'test_file'

        response = requests.delete(f'{HTTP_API_ROOT}/files/test_file')
        assert response.status_code == 200

        files_list = self.get_files_list()
        assert len(files_list) == 0

        with open(test_csv_path) as td:
            files = {
                'file': ('test_data.csv', td, 'text/csv'),
                'original_file_name': (None, 'super_test_data.csv')  # optional
            }

            response = requests.request('PUT', f'{HTTP_API_ROOT}/files/test_file', files=files, json=None, params=None, data=None)
            assert response.status_code == 200

        with open(small_test_csv_path) as td:
            files = {
                'file': ('small_test_data.csv', td, 'text/csv')
            }

            response = requests.request('PUT', f'{HTTP_API_ROOT}/files/small_test_file', files=files, json=None, params=None, data=None)
            assert response.status_code == 200

    def test_sql_general_syntax(self):
        ''' test sql in general
        '''
        select_const_int = [
            'select 1',
            'select 1;',
            'SELECT 1',
            'Select 1',
            '   select   1   ',
            '''   select
                  1;
            '''
        ]
        select_const_int_alias = [
            'select 1 as `2`',
            # "select 1 as '2'",     https://github.com/mindsdb/mindsdb_sql/issues/198
            'select 1 as "2"',
            'select 1 `2`',
            # "select 1 '2'",     https://github.com/mindsdb/mindsdb_sql/issues/198
            'select 1 "2"',
        ]
        select_const_str = [
            'select "a"',
            "select 'a'"
        ]
        select_const_str_alias = [
            'select "a" as b',
            "select 'a' as b",
            'select "a" b',
            # 'select "a" "b"',   # => ab
            'select "a" `b`',
            # "select 'a' 'b'"    # => ab
        ]
        bunch = [{
            'queries': select_const_int,
            'result': 1,
            'alias': '1'
        }, {
            'queries': select_const_int_alias,
            'result': 1,
            'alias': '2'
        }, {
            'queries': select_const_str,
            'result': 'a',
            'alias': 'a'
        }, {
            'queries': select_const_str_alias,
            'result': 'a',
            'alias': 'b'
        }]
        for group in bunch:
            queries = group['queries']
            expected_result = group['result']
            expected_alias = group['alias']
            for query in queries:
                print(query)
                resp = self.sql_via_http(query, RESPONSE_TYPE.TABLE)
                try:
                    assert len(resp['column_names']) == 1
                    assert resp['column_names'][0] == expected_alias
                    assert len(resp['data']) == 1
                    assert len(resp['data'][0]) == 1
                    assert resp['data'][0][0] == expected_result
                except Exception:
                    print(f'Error in query: {query}')
                    raise

    def test_context_changing(self):
        resp = self.sql_via_http('use mindsdb', RESPONSE_TYPE.OK)
        assert resp['context']['db'] == 'mindsdb'

        resp_1 = self.sql_via_http('show tables', RESPONSE_TYPE.TABLE)
        table_names = [x[0] for x in resp_1['data']]
        assert 'test_file' not in table_names
        assert 'models' in table_names
        assert 'models_versions' in table_names

        resp = self.sql_via_http('use files', RESPONSE_TYPE.OK)
        assert resp['context']['db'] == 'files'

        resp_4 = self.sql_via_http('show tables', RESPONSE_TYPE.TABLE)
        table_names = [x[0] for x in resp_4['data']]
        assert 'test_file' in table_names
        assert 'models' not in table_names
        assert 'models_versions' not in table_names

    def test_special_queries(self):
        # "show databases;",
        # "show schemas;",
        # "show tables;",
        # "show tables from mindsdb;",
        # "show full tables from mindsdb;",
        # "show variables;",
        # "show session status;",
        # "show global variables;",
        # "show engines;",
        # "show warnings;",
        # "show charset;",
        # "show collation;",
        # "show models;",
        # "show function status where db = 'mindsdb';",
        # "show procedure status where db = 'mindsdb';",
        empty_table = [
            "show function status",
            "show function status where db = 'mindsdb'",
            "show procedure status",
            "show procedure status where db = 'mindsdb'",
            "show warnings"
        ]
        for query in empty_table:
            try:
                print(query)
                resp = self.sql_via_http(query, RESPONSE_TYPE.TABLE)
                assert len(resp['data']) == 0
            except Exception:
                print(f'Error in query: {query}')
                raise

        not_empty_table = [
            "show databases",
            "show schemas",
            "show variables",
            "show session status",
            "show global variables",
            "show engines",
            "show charset",
            "show collation"
        ]
        for query in not_empty_table:
            try:
                print(query)
                resp = self.sql_via_http(query, RESPONSE_TYPE.TABLE)
                assert len(resp['data']) > 0
            except Exception:
                print(f'Error in query: {query}')
                raise

        # show database should be same as show schemas
        try:
            query = 'show databases'
            resp = self.sql_via_http(query, RESPONSE_TYPE.TABLE)
            assert len(resp['column_names']) == 1
            assert resp['column_names'][0] == 'Database'
            db_names = [x[0].lower() for x in resp['data']]
            assert 'information_schema' in db_names
            assert 'mindsdb' in db_names
            assert 'files' in db_names
        except Exception:
            print(f'Error in query: {query}')
            raise

    def test_show_tables(self):
        self.sql_via_http('use mindsdb', RESPONSE_TYPE.OK)

        resp_1 = self.sql_via_http('show tables', RESPONSE_TYPE.TABLE)
        resp_2 = self.sql_via_http('show tables from mindsdb', RESPONSE_TYPE.TABLE)
        resp_3 = self.sql_via_http('show full tables from mindsdb', RESPONSE_TYPE.TABLE)
        assert resp_1['data'].sort() == resp_2['data'].sort()
        assert resp_1['data'].sort() == resp_3['data'].sort()

    @pytest.mark.parametrize("db", ['postgres_db', 'mysql_db', 'maria_db'])
    def test_sql_create_database(self, db, subtests):
        ''' sql-via-http:
            'create database' for each db
            'drop database' for each db
            'create database' for each db
        '''
        db_data = getattr(self, db)
        db_type = db_data['type']
        db_creds = db_data['connection_data']
        queries = [
            {
                'create': 'CREATE DATABASE',
                'drop': 'DROP DATABASE'
            }, {
                'create': 'CREATE DATABASE',
                'drop': None
            }
        ]
        created_db_names = []
        for query in queries:
            create_query = query['create']
            drop_query = query['drop']
            db_name = db_type.upper()
            created_db_names.append(db_name)
            with subtests.test(msg=f'{db_type}', create_query=create_query, drop_query=drop_query, db_name=db_name):
                query = f"""
                    {create_query} {db_name}
                    WITH ENGINE = '{db_type}',
                    PARAMETERS = {json.dumps(db_creds)};
                """
                self.sql_via_http(query, RESPONSE_TYPE.OK)
                assert db_name in self.show_databases()
                if drop_query is not None:
                    self.sql_via_http(f'{drop_query} {db_name}', RESPONSE_TYPE.OK)
                    assert db_name.upper() not in self.show_databases()

        resp = self.sql_via_http('show databases', RESPONSE_TYPE.TABLE)
        db_names = [x[0] for x in resp['data']]
        for name in created_db_names:
            assert name in db_names

    def test_sql_select_from_file(self):
        self.sql_via_http('use mindsdb', RESPONSE_TYPE.OK)
        resp = self.sql_via_http('select * from files.test_file', RESPONSE_TYPE.TABLE)
        assert len(resp['data']) == 50
        assert len(resp['column_names']) == 8

        resp = self.sql_via_http('select rental_price, rental_price as rp1, rental_price rp2 from files.test_file limit 10', RESPONSE_TYPE.TABLE)
        assert len(resp['data']) == 10
        assert resp['column_names'] == ['rental_price', 'rp1', 'rp2']
        assert resp['data'][0][0] == resp['data'][0][1] and resp['data'][0][0] == resp['data'][0][2]

    def test_sql_create_predictor(self):
        resp = self.sql_via_http('show models', RESPONSE_TYPE.TABLE)
        assert len(resp['data']) == 0

        self.sql_via_http('''
            create predictor p_test_1
            from files (select sqft, location, rental_price from test_file limit 30)
            predict rental_price
        ''', RESPONSE_TYPE.TABLE)
        status = self.await_model('p_test_1', timeout=120)
        assert status == 'complete'

        resp = self.sql_via_http('''
            select * from mindsdb.p_test_1 where sqft = 1000
        ''', RESPONSE_TYPE.TABLE)
        sqft_index = resp['column_names'].index('sqft')
        rental_price_index = resp['column_names'].index('rental_price')
        assert len(resp['data']) == 1
        assert resp['data'][0][sqft_index] == 1000
        assert resp['data'][0][rental_price_index] > 0

        resp = self.sql_via_http('''
            select * from files.small_test_file ta join mindsdb.p_test_1
        ''', RESPONSE_TYPE.TABLE)
        rental_price_index = resp['column_names'].index('rental_price')
        assert len(resp['data']) == 5
        # FIXME rental price is str instead of float
        # for row in resp['data']:
        #     self.assertTrue(row[rental_price_index] > 0)

        # test http api
        project_name = 'mindsdb'
        model_name = 'p_test_1'

        # list projects
        response = self.api_request('get', '/projects')
        assert response.status_code == 200, 'Error to get list of projects'

        projects = [i['name'] for i in response.json()]
        assert project_name in projects

        # list models
        response = self.api_request('get', f'/projects/{project_name}/models')
        assert response.status_code == 200, 'Error to get list of models'
        models = [i['name'] for i in response.json()]
        assert model_name in models

        # prediction
        payload = {
            'data': [{'sqft': '1000'},
                     {'sqft': '500'}]
        }
        response = self.api_request('post', f'/projects/{project_name}/models/{model_name}/predict', payload=payload)
        assert response.status_code == 200, 'Error to make prediction'

        # 2 prediction result
        assert len(response.json()) == 2

        # 1st version of model
        response = self.api_request('post', f'/projects/{project_name}/models/{model_name}.1/predict', payload=payload)
        assert response.status_code == 200, 'Error to make prediction'

        assert len(response.json()) == 2

    @pytest.mark.parametrize("method,payload,expected_code,result,headers", [
        ("post", {}, 200, {}, {"company-id": "1"}),
        ("get", {}, 200, {}, {"company-id": "1"}),
        ("post", {"tab1": "select * from foo.bar limit 1"}, 200, {}, {"company-id": "1"}),
        ("get", {}, 200, {"tab1": "select * from foo.bar limit 1"}, {"company-id": "1"}),
        ("get", {}, 200, {}, {"company-id": "2"}),
    ])
    def test_tabs(self, method, payload, expected_code, result, headers):
        uri = '/tabs/'
        call_desc = f"{method.upper()} - {uri} payload={payload} headers={headers}"
        resp = self.api_request(method, uri, payload=payload, headers=headers)
        assert resp.status_code == expected_code, \
               f"expected to have {expected_code} for {call_desc}, but got {resp.status_code}"
        # no needs to check reponse body for POST request
        if method != "post":
            assert result == resp.json(), \
                   f"expected to have {result} for {call_desc}, but got {resp.json()}"
