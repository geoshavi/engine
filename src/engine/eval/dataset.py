"""The evaluation benchmark dataset: 20 tasks, each with a broken and a
clean version, spanning 4 benchmark categories (correctness, security,
quality, edge_case) -- 40 total cases.

The benchmark's own category taxonomy (correctness/security/quality/
edge_case) is intentionally separate from ``expected_defect_category``,
which must be one of the three dimensions the judge schema actually
validates against (verification/rubric.py's DIMENSIONS: CORRECTNESS,
SECURITY, CODE-QUALITY). edge_case tasks are all correctness-flavored bugs
at input/data boundaries -- there is no fourth judge dimension for "edge
case", so every edge_case task's expected_defect_category is CORRECTNESS.

Every snippet (broken and clean) is written to be ruff- and mypy-clean on
its own merits: broken versions carry a genuine semantic/security/
structural defect invisible to static linting, never a lint or type error.
If a snippet tripped ruff or mypy, verdict.gate() would return UNVERIFIED
for reasons unrelated to the judge, contaminating what this benchmark
measures. None of the snippets include test_*.py files, so the pytest gate
auto-passes ("no test files present") for every case -- automated_results
should always pass, and the only source of UNVERIFIED for "broken" cases
should be genuine judge-detected defects.

Deliberately mixes obvious anchor cases (SQL injection, mutable default
argument) with subtler ones the judge lens prompts don't name explicitly
(weak randomness for tokens, SSRF, timing-attack comparison, Unicode
truncation, non-atomic increment) so the benchmark tests generalization,
not prompt-keyword matching.
"""

from dataclasses import dataclass

BENCHMARK_NAME = "engine-review-benchmark"
BENCHMARK_VERSION = "v1"
DATASET_VERSION = "v1"

CATEGORIES = ("correctness", "security", "quality", "edge_case")
# The only three dimensions the judge schema (verification/rubric.py) accepts.
JUDGE_DIMENSIONS = ("CORRECTNESS", "SECURITY", "CODE-QUALITY")


@dataclass(frozen=True)
class EvalCase:
    eval_case_id: str
    category: str
    task_text: str
    files: dict[str, str]
    expected_verdict: str  # "OK" | "UNVERIFIED"
    expected_defect_category: str | None  # one of JUDGE_DIMENSIONS, or None for clean cases


@dataclass(frozen=True)
class EvalTask:
    task_id: str
    category: str
    task_text: str
    expected_defect_category: str
    broken_files: dict[str, str]
    clean_files: dict[str, str]


TASKS: list[EvalTask] = [
    # ---------------------------------------------------------------- correctness
    EvalTask(
        task_id="correctness-01",
        category="correctness",
        task_text=(
            "Implement paginate(items, page, page_size) using 1-indexed pages "
            "(page=1 is the first page) that returns the correct slice of items for that page."
        ),
        expected_defect_category="CORRECTNESS",
        broken_files={
            "solution.py": (
                "def paginate(items: list[int], page: int, page_size: int) -> list[int]:\n"
                "    start = page * page_size\n"
                "    end = start + page_size\n"
                "    return items[start:end]\n"
            )
        },
        clean_files={
            "solution.py": (
                "def paginate(items: list[int], page: int, page_size: int) -> list[int]:\n"
                "    start = (page - 1) * page_size\n"
                "    end = start + page_size\n"
                "    return items[start:end]\n"
            )
        },
    ),
    EvalTask(
        task_id="correctness-02",
        category="correctness",
        task_text=(
            "Implement is_close_enough(a, b) -> bool that returns True if two floats are "
            "close enough to be considered equal for currency comparison (within 0.01)."
        ),
        expected_defect_category="CORRECTNESS",
        broken_files={
            "solution.py": (
                "def is_close_enough(a: float, b: float) -> bool:\n"
                "    return a == b\n"
            )
        },
        clean_files={
            "solution.py": (
                "def is_close_enough(a: float, b: float) -> bool:\n"
                "    return abs(a - b) < 0.01\n"
            )
        },
    ),
    EvalTask(
        task_id="correctness-03",
        category="correctness",
        task_text=(
            "Implement can_edit(is_admin, is_owner, is_archived) -> bool: a user can edit "
            "if (they are an admin OR the owner) AND the resource is not archived."
        ),
        expected_defect_category="CORRECTNESS",
        broken_files={
            "solution.py": (
                "def can_edit(is_admin: bool, is_owner: bool, is_archived: bool) -> bool:\n"
                "    return is_admin or is_owner and not is_archived\n"
            )
        },
        clean_files={
            "solution.py": (
                "def can_edit(is_admin: bool, is_owner: bool, is_archived: bool) -> bool:\n"
                "    return (is_admin or is_owner) and not is_archived\n"
            )
        },
    ),
    EvalTask(
        task_id="correctness-04",
        category="correctness",
        task_text=(
            "Implement top_n_by_score(items, n) -> list returning the n items with the "
            "HIGHEST score, ordered from highest to lowest. items is a list of (name, score) pairs."
        ),
        expected_defect_category="CORRECTNESS",
        broken_files={
            "solution.py": (
                "def top_n_by_score(items: list[tuple[str, int]], n: int) -> list[tuple[str, int]]:\n"
                "    return sorted(items, key=lambda x: x[1])[:n]\n"
            )
        },
        clean_files={
            "solution.py": (
                "def top_n_by_score(items: list[tuple[str, int]], n: int) -> list[tuple[str, int]]:\n"
                "    return sorted(items, key=lambda x: x[1], reverse=True)[:n]\n"
            )
        },
    ),
    EvalTask(
        task_id="correctness-05",
        category="correctness",
        task_text=(
            "Implement running_average(nums) -> list[float] returning the cumulative "
            "running average at each index i (the average of nums[0..i])."
        ),
        expected_defect_category="CORRECTNESS",
        broken_files={
            "solution.py": (
                "def running_average(nums: list[float]) -> list[float]:\n"
                "    result = []\n"
                "    for i, n in enumerate(nums, start=1):\n"
                "        total = n\n"
                "        result.append(total / i)\n"
                "    return result\n"
            )
        },
        clean_files={
            "solution.py": (
                "def running_average(nums: list[float]) -> list[float]:\n"
                "    result = []\n"
                "    total = 0.0\n"
                "    for i, n in enumerate(nums, start=1):\n"
                "        total += n\n"
                "        result.append(total / i)\n"
                "    return result\n"
            )
        },
    ),
    # ------------------------------------------------------------------- security
    EvalTask(
        task_id="security-01",
        category="security",
        task_text=(
            "Implement get_user_by_email(conn, email) that queries the users table for a "
            "matching email and returns the row."
        ),
        expected_defect_category="SECURITY",
        broken_files={
            "solution.py": (
                "import sqlite3\n\n\n"
                "def get_user_by_email(conn: sqlite3.Connection, email: str) -> sqlite3.Row | None:\n"
                "    cursor = conn.execute(f\"SELECT * FROM users WHERE email = '{email}'\")\n"
                "    return cursor.fetchone()\n"
            )
        },
        clean_files={
            "solution.py": (
                "import sqlite3\n\n\n"
                "def get_user_by_email(conn: sqlite3.Connection, email: str) -> sqlite3.Row | None:\n"
                "    cursor = conn.execute(\"SELECT * FROM users WHERE email = ?\", (email,))\n"
                "    return cursor.fetchone()\n"
            )
        },
    ),
    EvalTask(
        task_id="security-02",
        category="security",
        task_text=(
            "Implement convert_to_png(filename) that shells out to an image converter to "
            "produce filename + '.png'."
        ),
        expected_defect_category="SECURITY",
        broken_files={
            "solution.py": (
                "import subprocess\n\n\n"
                "def convert_to_png(filename: str) -> None:\n"
                "    subprocess.run(f\"convert {filename} {filename}.png\", shell=True, check=True)\n"
            )
        },
        clean_files={
            "solution.py": (
                "import subprocess\n\n\n"
                "def convert_to_png(filename: str) -> None:\n"
                "    subprocess.run([\"convert\", filename, f\"{filename}.png\"], check=True)\n"
            )
        },
    ),
    EvalTask(
        task_id="security-03",
        category="security",
        task_text=(
            "Implement generate_reset_token() -> str returning a random 32-character hex "
            "token for password-reset links."
        ),
        expected_defect_category="SECURITY",
        broken_files={
            "solution.py": (
                "import random\n\n\n"
                "def generate_reset_token() -> str:\n"
                "    return \"\".join(random.choice(\"0123456789abcdef\") for _ in range(32))\n"
            )
        },
        clean_files={
            "solution.py": (
                "import secrets\n\n\n"
                "def generate_reset_token() -> str:\n"
                "    return secrets.token_hex(16)\n"
            )
        },
    ),
    EvalTask(
        task_id="security-04",
        category="security",
        task_text=(
            "Implement is_safe_fetch_target(host) -> bool used to guard a URL-preview "
            "feature against fetching internal/private network addresses (SSRF)."
        ),
        expected_defect_category="SECURITY",
        broken_files={
            "solution.py": (
                "def is_safe_fetch_target(host: str) -> bool:\n"
                "    return True\n"
            )
        },
        clean_files={
            "solution.py": (
                "import ipaddress\n"
                "import socket\n\n\n"
                "def is_safe_fetch_target(host: str) -> bool:\n"
                "    try:\n"
                "        addr = socket.gethostbyname(host)\n"
                "        ip = ipaddress.ip_address(addr)\n"
                "    except (OSError, ValueError):\n"
                "        return False\n"
                "    return not (ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved)\n"
            )
        },
    ),
    EvalTask(
        task_id="security-05",
        category="security",
        task_text=(
            "Implement verify_signature(expected, provided) -> bool used to authenticate "
            "an incoming webhook by comparing signatures."
        ),
        expected_defect_category="SECURITY",
        broken_files={
            "solution.py": (
                "def verify_signature(expected: str, provided: str) -> bool:\n"
                "    return expected == provided\n"
            )
        },
        clean_files={
            "solution.py": (
                "import hmac\n\n\n"
                "def verify_signature(expected: str, provided: str) -> bool:\n"
                "    return hmac.compare_digest(expected, provided)\n"
            )
        },
    ),
    # -------------------------------------------------------------------- quality
    EvalTask(
        task_id="quality-01",
        category="quality",
        task_text=(
            "Implement register_user(name, email, password) -> dict that validates the "
            "inputs, hashes the password, and returns the new user record ready to store."
        ),
        expected_defect_category="CODE-QUALITY",
        broken_files={
            "solution.py": (
                "import hashlib\n"
                "import re\n\n\n"
                "def register_user(name: str, email: str, password: str) -> dict[str, str]:\n"
                "    if not name or len(name) < 2:\n"
                "        raise ValueError(\"name too short\")\n"
                "    if not re.match(r\"^[^@]+@[^@]+\\.[^@]+$\", email):\n"
                "        raise ValueError(\"invalid email\")\n"
                "    if len(password) < 8:\n"
                "        raise ValueError(\"password too short\")\n"
                "    has_digit = any(c.isdigit() for c in password)\n"
                "    if not has_digit:\n"
                "        raise ValueError(\"password needs a digit\")\n"
                "    salt = \"static-salt\"\n"
                "    hashed = hashlib.sha256((password + salt).encode()).hexdigest()\n"
                "    record = {\"name\": name.strip(), \"email\": email.lower(), \"password_hash\": hashed}\n"
                "    subject = \"Welcome, \" + name\n"
                "    body = \"Your account \" + email + \" is ready.\"\n"
                "    print(f\"EMAIL to {email}: {subject} -- {body}\")\n"
                "    return record\n"
            )
        },
        clean_files={
            "solution.py": (
                "import hashlib\n"
                "import re\n\n\n"
                "def _validate_name(name: str) -> str:\n"
                "    if not name or len(name) < 2:\n"
                "        raise ValueError(\"name too short\")\n"
                "    return name.strip()\n\n\n"
                "def _validate_email(email: str) -> str:\n"
                "    if not re.match(r\"^[^@]+@[^@]+\\.[^@]+$\", email):\n"
                "        raise ValueError(\"invalid email\")\n"
                "    return email.lower()\n\n\n"
                "def _hash_password(password: str) -> str:\n"
                "    if len(password) < 8 or not any(c.isdigit() for c in password):\n"
                "        raise ValueError(\"password too weak\")\n"
                "    salt = \"static-salt\"\n"
                "    return hashlib.sha256((password + salt).encode()).hexdigest()\n\n\n"
                "def _send_welcome_email(name: str, email: str) -> None:\n"
                "    print(f\"EMAIL to {email}: Welcome, {name} -- Your account {email} is ready.\")\n\n\n"
                "def register_user(name: str, email: str, password: str) -> dict[str, str]:\n"
                "    clean_name = _validate_name(name)\n"
                "    clean_email = _validate_email(email)\n"
                "    password_hash = _hash_password(password)\n"
                "    record = {\"name\": clean_name, \"email\": clean_email, \"password_hash\": password_hash}\n"
                "    _send_welcome_email(clean_name, clean_email)\n"
                "    return record\n"
            )
        },
    ),
    EvalTask(
        task_id="quality-02",
        category="quality",
        task_text=(
            "Implement validate_signup(email, age) and validate_profile_update(email, age), "
            "each returning True if email contains '@' with a '.' after it, and age is 13-120."
        ),
        expected_defect_category="CODE-QUALITY",
        broken_files={
            "solution.py": (
                "def validate_signup(email: str, age: int) -> bool:\n"
                "    if \"@\" not in email:\n"
                "        return False\n"
                "    domain = email.partition(\"@\")[2]\n"
                "    if \".\" not in domain:\n"
                "        return False\n"
                "    return 13 <= age <= 120\n\n\n"
                "def validate_profile_update(email: str, age: int) -> bool:\n"
                "    if \"@\" not in email:\n"
                "        return False\n"
                "    domain = email.partition(\"@\")[2]\n"
                "    if \".\" not in domain:\n"
                "        return False\n"
                "    return 13 <= age <= 120\n"
            )
        },
        clean_files={
            "solution.py": (
                "def _is_valid_email_and_age(email: str, age: int) -> bool:\n"
                "    if \"@\" not in email:\n"
                "        return False\n"
                "    domain = email.partition(\"@\")[2]\n"
                "    if \".\" not in domain:\n"
                "        return False\n"
                "    return 13 <= age <= 120\n\n\n"
                "def validate_signup(email: str, age: int) -> bool:\n"
                "    return _is_valid_email_and_age(email, age)\n\n\n"
                "def validate_profile_update(email: str, age: int) -> bool:\n"
                "    return _is_valid_email_and_age(email, age)\n"
            )
        },
    ),
    EvalTask(
        task_id="quality-03",
        category="quality",
        task_text=(
            "Implement a function that returns an existing user dict from a users-by-id "
            "dict if present, otherwise creates and stores a new default user record."
        ),
        expected_defect_category="CODE-QUALITY",
        broken_files={
            "solution.py": (
                "def get_user(users: dict[int, dict[str, str]], user_id: int) -> dict[str, str]:\n"
                "    if user_id in users:\n"
                "        return users[user_id]\n"
                "    new_user = {\"id\": str(user_id), \"name\": \"New User\"}\n"
                "    users[user_id] = new_user\n"
                "    return new_user\n"
            )
        },
        clean_files={
            "solution.py": (
                "def get_or_create_user(users: dict[int, dict[str, str]], user_id: int) -> dict[str, str]:\n"
                "    if user_id in users:\n"
                "        return users[user_id]\n"
                "    new_user = {\"id\": str(user_id), \"name\": \"New User\"}\n"
                "    users[user_id] = new_user\n"
                "    return new_user\n"
            )
        },
    ),
    EvalTask(
        task_id="quality-04",
        category="quality",
        task_text=(
            "Implement classify_order(total, is_member, has_coupon, in_stock) -> str "
            "returning 'rejected' if not in_stock, else a discount tier based on the other flags."
        ),
        expected_defect_category="CODE-QUALITY",
        broken_files={
            "solution.py": (
                "def classify_order(total: float, is_member: bool, has_coupon: bool, in_stock: bool) -> str:\n"
                "    if in_stock:\n"
                "        if is_member:\n"
                "            if has_coupon:\n"
                "                if total > 100:\n"
                "                    return \"vip_discount\"\n"
                "                else:\n"
                "                    return \"member_coupon_discount\"\n"
                "            else:\n"
                "                if total > 100:\n"
                "                    return \"member_discount\"\n"
                "                else:\n"
                "                    return \"member_standard\"\n"
                "        else:\n"
                "            if has_coupon:\n"
                "                return \"coupon_discount\"\n"
                "            else:\n"
                "                return \"standard\"\n"
                "    else:\n"
                "        return \"rejected\"\n"
            )
        },
        clean_files={
            "solution.py": (
                "def classify_order(total: float, is_member: bool, has_coupon: bool, in_stock: bool) -> str:\n"
                "    if not in_stock:\n"
                "        return \"rejected\"\n"
                "    if is_member and has_coupon and total > 100:\n"
                "        return \"vip_discount\"\n"
                "    if is_member and has_coupon:\n"
                "        return \"member_coupon_discount\"\n"
                "    if is_member and total > 100:\n"
                "        return \"member_discount\"\n"
                "    if is_member:\n"
                "        return \"member_standard\"\n"
                "    if has_coupon:\n"
                "        return \"coupon_discount\"\n"
                "    return \"standard\"\n"
            )
        },
    ),
    EvalTask(
        task_id="quality-05",
        category="quality",
        task_text=(
            "Implement compute_ticket_price(age, base_price) -> float: children under 18 "
            "get a 15% discount off the base price, no other adjustments."
        ),
        expected_defect_category="CODE-QUALITY",
        broken_files={
            "solution.py": (
                "def compute_ticket_price(age: int, base_price: float) -> float:\n"
                "    if age < 18:\n"
                "        return base_price * 0.85\n"
                "    return base_price\n"
            )
        },
        clean_files={
            "solution.py": (
                "CHILD_AGE_CUTOFF = 18\n"
                "CHILD_DISCOUNT_RATE = 0.15\n\n\n"
                "def compute_ticket_price(age: int, base_price: float) -> float:\n"
                "    if age < CHILD_AGE_CUTOFF:\n"
                "        return base_price * (1 - CHILD_DISCOUNT_RATE)\n"
                "    return base_price\n"
            )
        },
    ),
    # ------------------------------------------------------------------ edge_case
    EvalTask(
        task_id="edge_case-01",
        category="edge_case",
        task_text=(
            "Implement average(nums) -> float returning the arithmetic mean, or 0.0 for an "
            "empty list."
        ),
        expected_defect_category="CORRECTNESS",
        broken_files={
            "solution.py": (
                "def average(nums: list[float]) -> float:\n"
                "    return sum(nums) / len(nums)\n"
            )
        },
        clean_files={
            "solution.py": (
                "def average(nums: list[float]) -> float:\n"
                "    if not nums:\n"
                "        return 0.0\n"
                "    return sum(nums) / len(nums)\n"
            )
        },
    ),
    EvalTask(
        task_id="edge_case-02",
        category="edge_case",
        task_text=(
            "Implement get_user_email(user) -> str | None that safely reads "
            "user['profile']['email'], returning None if any part of that path is missing, "
            "without raising."
        ),
        expected_defect_category="CORRECTNESS",
        broken_files={
            "solution.py": (
                "def get_user_email(user: dict) -> str | None:\n"
                "    return user[\"profile\"][\"email\"]\n"
            )
        },
        clean_files={
            "solution.py": (
                "def get_user_email(user: dict) -> str | None:\n"
                "    profile = user.get(\"profile\")\n"
                "    if not isinstance(profile, dict):\n"
                "        return None\n"
                "    email = profile.get(\"email\")\n"
                "    return email if isinstance(email, str) else None\n"
            )
        },
    ),
    EvalTask(
        task_id="edge_case-03",
        category="edge_case",
        task_text=(
            "Implement truncate(text, max_chars) -> str that shortens text to at most "
            "max_chars characters, without corrupting multi-byte Unicode characters."
        ),
        expected_defect_category="CORRECTNESS",
        broken_files={
            "solution.py": (
                "def truncate(text: str, max_chars: int) -> str:\n"
                "    return text.encode(\"utf-8\")[:max_chars].decode(\"utf-8\")\n"
            )
        },
        clean_files={
            "solution.py": (
                "def truncate(text: str, max_chars: int) -> str:\n"
                "    return text[:max_chars]\n"
            )
        },
    ),
    EvalTask(
        task_id="edge_case-04",
        category="edge_case",
        task_text=(
            "Implement is_business_hours(hour) -> bool returning True for hours in [9, 17) "
            "using 24-hour time -- 9:00 is open, 17:00 is already closed."
        ),
        expected_defect_category="CORRECTNESS",
        broken_files={
            "solution.py": (
                "def is_business_hours(hour: int) -> bool:\n"
                "    return 9 <= hour <= 17\n"
            )
        },
        clean_files={
            "solution.py": (
                "def is_business_hours(hour: int) -> bool:\n"
                "    return 9 <= hour < 17\n"
            )
        },
    ),
    EvalTask(
        task_id="edge_case-05",
        category="edge_case",
        task_text=(
            "Implement a Counter class with increment() and a value property, safe to call "
            "from multiple threads concurrently."
        ),
        expected_defect_category="CORRECTNESS",
        broken_files={
            "solution.py": (
                "class Counter:\n"
                "    def __init__(self) -> None:\n"
                "        self._value = 0\n\n"
                "    def increment(self) -> None:\n"
                "        current = self._value\n"
                "        self._value = current + 1\n\n"
                "    @property\n"
                "    def value(self) -> int:\n"
                "        return self._value\n"
            )
        },
        clean_files={
            "solution.py": (
                "import threading\n\n\n"
                "class Counter:\n"
                "    def __init__(self) -> None:\n"
                "        self._value = 0\n"
                "        self._lock = threading.Lock()\n\n"
                "    def increment(self) -> None:\n"
                "        with self._lock:\n"
                "            self._value += 1\n\n"
                "    @property\n"
                "    def value(self) -> int:\n"
                "        return self._value\n"
            )
        },
    ),
]


def _build_cases(tasks: list[EvalTask]) -> list[EvalCase]:
    cases: list[EvalCase] = []
    for task in tasks:
        cases.append(
            EvalCase(
                eval_case_id=f"{task.task_id}-broken",
                category=task.category,
                task_text=task.task_text,
                files=task.broken_files,
                expected_verdict="UNVERIFIED",
                expected_defect_category=task.expected_defect_category,
            )
        )
        cases.append(
            EvalCase(
                eval_case_id=f"{task.task_id}-clean",
                category=task.category,
                task_text=task.task_text,
                files=task.clean_files,
                expected_verdict="OK",
                expected_defect_category=None,
            )
        )
    return cases


CASES: list[EvalCase] = _build_cases(TASKS)


def validate_dataset(cases: list[EvalCase]) -> list[str]:
    """Structural validation only -- never judges whether a task is a good
    benchmark case, only whether it's well-formed enough to run. Mirrors
    execution_plan.py's validate_execution_plan: a pure function, no I/O,
    called by --dry-run before any LLM call is made.
    """
    errors: list[str] = []
    seen_ids: set[str] = set()

    for i, case in enumerate(cases):
        if case.eval_case_id in seen_ids:
            errors.append(f"cases[{i}]: duplicate eval_case_id {case.eval_case_id!r}")
        seen_ids.add(case.eval_case_id)

        if case.category not in CATEGORIES:
            errors.append(f"cases[{i}]: unknown category {case.category!r}, expected one of {CATEGORIES}")

        if case.expected_verdict not in ("OK", "UNVERIFIED"):
            errors.append(
                f"cases[{i}]: expected_verdict must be 'OK' or 'UNVERIFIED', got {case.expected_verdict!r}"
            )

        if case.expected_defect_category is not None and case.expected_defect_category not in JUDGE_DIMENSIONS:
            errors.append(
                f"cases[{i}]: expected_defect_category must be one of {JUDGE_DIMENSIONS} or None, "
                f"got {case.expected_defect_category!r}"
            )

        if not case.files:
            errors.append(f"cases[{i}]: files must not be empty")

        if not case.task_text.strip():
            errors.append(f"cases[{i}]: task_text must not be empty")

    return errors
