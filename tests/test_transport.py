"""Unit tests for IPP encoding, decoding, and transport."""

import unittest
from g640rip.transport.constants import (
    IPP_OP_PRINT_JOB,
    IPP_VERSION_2_0,
    TAG_CHARSET,
    TAG_NATURAL_LANGUAGE,
    TAG_URI,
    TAG_NAME_WITHOUT_LANGUAGE,
    TAG_MIME_MEDIA_TYPE,
    TAG_KEYWORD,
    TAG_INTEGER,
    STATUS_OK,
)
from g640rip.transport.ipp_client import IPPMessage
from g640rip.transport.discovery import _parse_txt_records, _parse_urf_field


class TestIPPTransport(unittest.TestCase):
    def test_ipp_message_encode_decode(self):
        msg = IPPMessage(version=IPP_VERSION_2_0, operation_or_status=IPP_OP_PRINT_JOB, request_id=42)
        msg.add_operation_attr(TAG_CHARSET, "attributes-charset", "utf-8")
        msg.add_operation_attr(TAG_NATURAL_LANGUAGE, "attributes-natural-language", "en-us")
        msg.add_operation_attr(TAG_URI, "printer-uri", "ipp://192.168.0.41:631/ipp/print")
        msg.add_operation_attr(TAG_NAME_WITHOUT_LANGUAGE, "job-name", "TestTarget")
        msg.add_operation_attr(TAG_MIME_MEDIA_TYPE, "document-format", "image/urf")

        msg.add_job_attr(TAG_KEYWORD, "media", "iso_a4_210x297mm")
        msg.add_job_attr(TAG_INTEGER, "copies", 1)

        payload = b"FAKE_URF_RASTER_DATA_BYTES"
        msg.data = payload

        encoded = msg.encode()
        self.assertTrue(len(encoded) > 50)

        # Decode back
        decoded = IPPMessage.decode(encoded)
        self.assertEqual(decoded.version, (2, 0))
        self.assertEqual(decoded.operation_or_status, IPP_OP_PRINT_JOB)
        self.assertEqual(decoded.request_id, 42)
        self.assertEqual(decoded.data, payload)

        op_names = [a.name for a in decoded.operation_attributes]
        self.assertIn("attributes-charset", op_names)
        self.assertIn("job-name", op_names)
        self.assertIn("document-format", op_names)

    def test_txt_record_parser(self):
        raw = "txtvers=1 rp=ipp/print qtotal=1 ty=Canon\\ G600\\ series pdl=image/urf,image/pwg-raster URF=V1.4,CP1,PQ3-5,RS600,SRGB24"
        records = _parse_txt_records(raw)
        self.assertEqual(records.get("rp"), "ipp/print")
        self.assertIn("image/urf", records.get("pdl", ""))

        urf_feats = _parse_urf_field(records.get("URF", ""))
        self.assertEqual(urf_feats.get("version"), "1.4")
        self.assertEqual(urf_feats.get("resolution"), "600")
        self.assertEqual(urf_feats.get("quality"), "3-5")


if __name__ == "__main__":
    unittest.main()

