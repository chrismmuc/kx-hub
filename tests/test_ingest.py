import json
import unittest
from unittest.mock import patch, MagicMock
import os
import requests

# By running with `python -m unittest discover`, the root directory is added to the path
# and we can do absolute imports from `src`.
from src.ingest import main

class TestIngestFunction(unittest.TestCase):

    @patch('src.ingest.main.PIPELINE_MANIFEST_PREFIX', 'manifests')
    @patch('src.ingest.main.PIPELINE_BUCKET', 'test-project-pipeline')
    @patch('src.ingest.main.PIPELINE_BUCKET', 'test-project-pipeline')
    @patch('src.ingest.main.PROJECT_ID', 'test-project')
    @patch('src.ingest.main.generate_run_id', return_value='2025-10-20T02-00-00Z-test1234')
    @patch('src.ingest.main._get_pubsub_publisher')
    @patch('src.ingest.main._get_storage_client')
    @patch('src.ingest.main._get_secret_client')
    def test_handler_success(self, mock_get_secret, mock_get_storage, mock_get_pubsub, mock_run_id):
        # Setup mocks returned by lazy getters
        mock_secret_client = MagicMock()
        mock_storage_client = MagicMock()
        mock_pubsub_client = MagicMock()

        mock_get_secret.return_value = mock_secret_client
        mock_get_storage.return_value = mock_storage_client
        mock_get_pubsub.return_value = mock_pubsub_client

        # Mock secrets
        mock_secret_client.access_secret_version.return_value.payload.data = b'fake-api-key'

        # Mock Readwise API response (returns books with nested highlights)
        with patch('src.ingest.main.requests.get') as mock_requests_get:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.raise_for_status.return_value = None
            mock_response.json.return_value = {
                'results': [{
                    'user_book_id': 123,
                    'title': 'Test Book',
                    'highlights': [{'text': 'Hello world'}]
                }],
                'nextPageCursor': None
            }
            mock_requests_get.return_value = mock_response

            # Mock GCS
            mock_raw_bucket = MagicMock()
            mock_manifest_bucket = MagicMock()
            mock_raw_blob = MagicMock()
            mock_manifest_blob = MagicMock()

            def bucket_side_effect(name):
                if name == 'test-project-raw-json':
                    return mock_raw_bucket
                elif name == 'test-project-pipeline':
                    return mock_manifest_bucket
                return MagicMock()

            mock_storage_client.bucket.side_effect = bucket_side_effect
            mock_raw_bucket.blob.return_value = mock_raw_blob
            mock_manifest_bucket.blob.return_value = mock_manifest_blob

            # Mock Pub/Sub
            mock_future = MagicMock()
            mock_future.result.return_value = 'message-id'
            mock_pubsub_client.publish.return_value = mock_future
            mock_pubsub_client.topic_path.return_value = 'projects/test/topics/daily-ingest'

            # Call the handler
            result = main.handler(event={}, context={})

            # Assertions
            self.assertEqual(result, 'OK')
            mock_secret_client.access_secret_version.assert_called_once()
            mock_requests_get.assert_called_once()
            self.assertEqual(mock_storage_client.bucket.call_count, 2)
            mock_raw_blob.upload_from_string.assert_called_once()
            mock_manifest_blob.upload_from_string.assert_called_once()
            mock_pubsub_client.publish.assert_called_once()
            published_payload = mock_pubsub_client.publish.call_args.args[1]
            message = json.loads(published_payload.decode("utf-8"))
            self.assertEqual(message["run_id"], '2025-10-20T02-00-00Z-test1234')
            self.assertEqual(message["item_count"], 1)
            manifest_kwargs = mock_manifest_blob.upload_from_string.call_args.kwargs
            manifest_body = json.loads(manifest_kwargs["data"])
            self.assertEqual(manifest_body["run_id"], '2025-10-20T02-00-00Z-test1234')
            self.assertEqual(manifest_body["item_count"], 1)
            self.assertEqual(manifest_body["items"][0]["id"], '123')

    @patch('src.ingest.main.PROJECT_ID', 'test-project')
    @patch('src.ingest.main._get_secret_client')
    @patch('src.ingest.main.requests.get')
    def test_handler_api_failure(self, mock_requests_get, mock_get_secret):
        # Setup mock
        mock_secret_client = MagicMock()
        mock_get_secret.return_value = mock_secret_client

        # Mock secrets
        mock_secret_client.access_secret_version.return_value.payload.data = b'fake-api-key'

        # Mock a failing Readwise API response
        mock_requests_get.side_effect = requests.exceptions.RequestException("API is down")

        # Call the handler and assert it raises an exception
        with self.assertRaises(requests.exceptions.RequestException):
            main.handler(event={}, context={})

if __name__ == '__main__':
    unittest.main()
