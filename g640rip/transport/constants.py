"""IPP protocol constants for Canon G640 micro-RIP."""

# IPP Versions
IPP_VERSION_1_1 = (1, 1)
IPP_VERSION_2_0 = (2, 0)

# IPP Operation IDs
IPP_OP_PRINT_JOB = 0x0002
IPP_OP_PRINT_URI = 0x0003
IPP_OP_VALIDATE_JOB = 0x0004
IPP_OP_CREATE_JOB = 0x0005
IPP_OP_SEND_DOCUMENT = 0x0006
IPP_OP_CANCEL_JOB = 0x0008
IPP_OP_GET_JOB_ATTRIBUTES = 0x0009
IPP_OP_GET_JOBS = 0x000A
IPP_OP_GET_PRINTER_ATTRIBUTES = 0x000B

# IPP Delimiter Tags
TAG_OPERATION_ATTRIBUTES = 0x01
TAG_JOB_ATTRIBUTES = 0x02
TAG_END_OF_ATTRIBUTES = 0x03
TAG_PRINTER_ATTRIBUTES = 0x04
TAG_UNSUPPORTED_ATTRIBUTES = 0x05

# IPP Value Tags
TAG_UNSUPPORTED = 0x10
TAG_UNKNOWN = 0x12
TAG_NO_VALUE = 0x13
TAG_INTEGER = 0x21
TAG_BOOLEAN = 0x22
TAG_ENUM = 0x23
TAG_OCTET_STRING = 0x30
TAG_DATETIME = 0x31
TAG_RESOLUTION = 0x32
TAG_RANGE_OF_INTEGER = 0x33
TAG_TEXT_WITH_LANGUAGE = 0x35
TAG_NAME_WITH_LANGUAGE = 0x36
TAG_TEXT_WITHOUT_LANGUAGE = 0x41
TAG_NAME_WITHOUT_LANGUAGE = 0x42
TAG_KEYWORD = 0x44
TAG_URI = 0x45
TAG_URI_SCHEME = 0x46
TAG_CHARSET = 0x47
TAG_NATURAL_LANGUAGE = 0x48
TAG_MIME_MEDIA_TYPE = 0x49

# IPP Status Codes
STATUS_OK = 0x0000
STATUS_OK_SUBST = 0x0001
STATUS_OK_CONFLICT = 0x0002
STATUS_CLIENT_BAD_REQUEST = 0x0400
STATUS_CLIENT_FORBIDDEN = 0x0401
STATUS_CLIENT_NOT_AUTHENTICATED = 0x0402
STATUS_CLIENT_NOT_AUTHORIZED = 0x0403
STATUS_CLIENT_NOT_POSSIBLE = 0x0404
STATUS_CLIENT_TIMEOUT = 0x0405
STATUS_CLIENT_NOT_FOUND = 0x0406
STATUS_CLIENT_GONE = 0x0407
STATUS_SERVER_INTERNAL_ERROR = 0x0500
STATUS_SERVER_OPERATION_NOT_SUPPORTED = 0x0501
STATUS_SERVER_SERVICE_UNAVAILABLE = 0x0502
STATUS_SERVER_VERSION_NOT_SUPPORTED = 0x0503
STATUS_SERVER_DEVICE_ERROR = 0x0504
STATUS_SERVER_TEMPORARY_ERROR = 0x0505
STATUS_SERVER_NOT_ACCEPTING_JOBS = 0x0506

# Print Quality Enums
PRINT_QUALITY_DRAFT = 3
PRINT_QUALITY_NORMAL = 4
PRINT_QUALITY_HIGH = 5

# Common Media Types for Canon G640
CANON_MEDIA_TYPES = {
    "glossy": "com.canon.mtgr",            # Photo Paper Plus Glossy II (PP-201/PP-301)
    "glossy2": "com.canon.mtgr",           # Photo Paper Plus Glossy II
    "plus_glossy_ii": "com.canon.mtgr",    # Photo Paper Plus Glossy II
    "luster": "com.canon.mtluster",        # Photo Paper Pro Luster (LU-101)
    "matte": "com.canon.mtmat",            # Matte Photo Paper (MP-101)
    "semigloss": "com.canon.mtsemisuper",  # Photo Paper Plus Semi-gloss (SG-201)
    "everyday_glossy": "com.canon.mtglossy",# Glossy Photo Paper (GP-501)
    "hires": "com.canon.mthires",          # High Resolution Paper (HR-101N)
    "plain": "stationery",                 # Plain Paper
    "photo": "photographic",
    "auto": "auto",
}

# Standard Page Dimensions in Points (72 dpi) and at 600 DPI
PAPER_SIZES = {
    "A4": {
        "width_mm": 210,
        "height_mm": 297,
        "width_600dpi": 4960,
        "height_600dpi": 7016,
        "media_name": "A4",
        "media_fullbleed": "A4.Fullbleed",
        "ipp_media": "iso_a4_210x297mm",
        "supports_borderless": True,
    },
    "4x6": {
        "width_mm": 101.6,
        "height_mm": 152.4,
        "width_600dpi": 2400,
        "height_600dpi": 3600,
        "media_name": "4x6",
        "media_fullbleed": "4x6.Fullbleed",
        "ipp_media": "na_index-4x6_4x6in",
        "supports_borderless": True,
    },
    "10x15": {
        "width_mm": 101.6,
        "height_mm": 152.4,
        "width_600dpi": 2400,
        "height_600dpi": 3600,
        "media_name": "4x6",
        "media_fullbleed": "4x6.Fullbleed",
        "ipp_media": "na_index-4x6_4x6in",
        "supports_borderless": True,
    },
    "5x7": {
        "width_mm": 127,
        "height_mm": 177.8,
        "width_600dpi": 3000,
        "height_600dpi": 4200,
        "media_name": "5x7",
        "media_fullbleed": "5x7.Fullbleed",
        "ipp_media": "na_5x7_5x7in",
        "supports_borderless": True,
    },
    "3.5x5": {
        "width_mm": 88.9,
        "height_mm": 127.0,
        "width_600dpi": 2100,
        "height_600dpi": 3000,
        "media_name": "3.5x5",
        "media_fullbleed": "3.5x5.Fullbleed",
        "ipp_media": "oe_photo-l_3.5x5in",
        "supports_borderless": True,
    },
    "Letter": {
        "width_mm": 215.9,
        "height_mm": 279.4,
        "width_600dpi": 5100,
        "height_600dpi": 6600,
        "media_name": "Letter",
        "media_fullbleed": "Letter.Fullbleed",
        "ipp_media": "na_letter_8.5x11in",
        "supports_borderless": True,
    },
    "8x10": {
        "width_mm": 203.2,
        "height_mm": 254.0,
        "width_600dpi": 4800,
        "height_600dpi": 6000,
        "media_name": "8x10",
        "media_fullbleed": "8x10.Fullbleed",
        "ipp_media": "na_govt-letter_8x10in",
        "supports_borderless": True,
    },
    "5x5": {
        "width_mm": 127.0,
        "height_mm": 127.0,
        "width_600dpi": 3000,
        "height_600dpi": 3000,
        "media_name": "5x5",
        "media_fullbleed": "5x5.Fullbleed",
        "ipp_media": "om_square-photo_127x127mm",
        "supports_borderless": True,
    },
    "Postcard": {
        "width_mm": 100.0,
        "height_mm": 148.0,
        "width_600dpi": 2362,
        "height_600dpi": 3496,
        "media_name": "Postcard",
        "media_fullbleed": "Postcard.Fullbleed",
        "ipp_media": "jpn_hagaki_100x148mm",
        "supports_borderless": True,
    },
    "A5": {
        "width_mm": 148,
        "height_mm": 210,
        "width_600dpi": 3496,
        "height_600dpi": 4960,
        "media_name": "A5",
        "media_fullbleed": "A5",
        "ipp_media": "iso_a5_148x210mm",
        "supports_borderless": False,
    },
}


def get_paper_spec(size_name: str) -> dict:
    """Retrieve paper specifications matching name or alias."""
    if not size_name:
        return PAPER_SIZES["4x6"]
    key = size_name.strip()
    for k, v in PAPER_SIZES.items():
        if k.lower() == key.lower():
            return v
    if any(x in key.lower() for x in ("4x6", "10x15", "small-photo")):
        return PAPER_SIZES["4x6"]
    if "a4" in key.lower():
        return PAPER_SIZES["A4"]
    return PAPER_SIZES.get(key, PAPER_SIZES["4x6"])

