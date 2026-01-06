import json
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from mxbi.tasks.cross_modal.trial_schema import Trial


class BundleValidationError(RuntimeError):
    def __init__(self, errors: list[str]) -> None:
        self.errors = errors
        super().__init__("\n".join(errors))


def assert_safe_internal_path(internal_path: str) -> None:
    if not internal_path:
        raise ValueError("Empty path is not allowed.")
    if internal_path.startswith(("/", "\\")):
        raise ValueError(f"Absolute paths are not allowed: '{internal_path}'")
    if "\\" in internal_path:
        raise ValueError(f"Backslashes are not allowed in bundle paths: '{internal_path}'")
    parts = internal_path.split("/")
    for part in parts:
        if not part:
            raise ValueError(f"Invalid path segment in '{internal_path}'")
        if part in {".", ".."}:
            raise ValueError(f"Path traversal is not allowed: '{internal_path}'")


class BundleCounts(BaseModel):
    model_config = ConfigDict(extra="allow")

    overallTrials: int = Field(alias="overallTrials")
    perSubjectTrials: dict[str, int] = Field(alias="perSubjectTrials")


class DatasetMeta(BaseModel):
    model_config = ConfigDict(extra="allow")

    dataset_id: str
    created_at: str
    source_data_dir_label: str
    subjects: list[str]
    seed_policy: dict[str, Any]
    generator_config: dict[str, Any]
    counts: dict[str, Any]


class ManifestExemplar(BaseModel):
    model_config = ConfigDict(extra="allow", populate_by_name=True)

    index: int
    relative_path: str = Field(validation_alias="relativePath")
    file_name: str = Field(validation_alias="fileName")


class ManifestIdentity(BaseModel):
    model_config = ConfigDict(extra="allow", populate_by_name=True)

    id: str
    image_exemplars: list[ManifestExemplar] = Field(validation_alias="imageExemplars")
    audio_exemplars: list[ManifestExemplar] = Field(validation_alias="audioExemplars")


class Manifest(BaseModel):
    model_config = ConfigDict(extra="allow", populate_by_name=True)

    meta: dict[str, Any]
    identities: list[ManifestIdentity]


class CrossModalBundleDir:
    def __init__(
        self,
        root_dir: Path,
        *,
        dataset_meta: DatasetMeta,
        manifest: Manifest,
        file_index: dict[str, Path],
        lower_to_actual: dict[str, str],
        trials_by_subject: dict[str, list[Trial]],
    ) -> None:
        self._root_dir = root_dir
        self._dataset_meta = dataset_meta
        self._manifest = manifest
        self._file_index = file_index
        self._lower_to_actual = lower_to_actual
        self._trials_by_subject = trials_by_subject

    @property
    def root_dir(self) -> Path:
        return self._root_dir

    @property
    def dataset_meta(self) -> DatasetMeta:
        return self._dataset_meta

    @property
    def manifest(self) -> Manifest:
        return self._manifest

    def subject_ids(self) -> list[str]:
        return list(self._dataset_meta.subjects)

    @classmethod
    def from_dir_path(cls, root_dir: Path) -> "CrossModalBundleDir":
        root_dir = root_dir.expanduser().resolve()
        errors: list[str] = []

        if not root_dir.exists():
            raise BundleValidationError([f"Bundle directory does not exist: {root_dir}"])
        if not root_dir.is_dir():
            raise BundleValidationError([f"Bundle path is not a directory: {root_dir}"])

        file_index, lower_to_actual, index_errors = cls._build_file_index(root_dir)
        errors.extend(index_errors)

        dataset_meta = cls._read_json_model(
            root_dir,
            file_index=file_index,
            lower_to_actual=lower_to_actual,
            internal_path="dataset_meta.json",
            model=DatasetMeta,
            errors=errors,
        )
        manifest = cls._read_json_model(
            root_dir,
            file_index=file_index,
            lower_to_actual=lower_to_actual,
            internal_path="manifest.json",
            model=Manifest,
            errors=errors,
        )

        cls._require_directory(root_dir / "media", errors, "Bundle is missing required directory: 'media/'")
        cls._require_directory(
            root_dir / "media" / "images",
            errors,
            "Bundle is missing required directory: 'media/images/'",
        )
        cls._require_directory(
            root_dir / "media" / "audio",
            errors,
            "Bundle is missing required directory: 'media/audio/'",
        )
        cls._require_directory(
            root_dir / "trial_sets",
            errors,
            "Bundle is missing required directory: 'trial_sets/'",
        )

        if dataset_meta is None or manifest is None:
            raise BundleValidationError(errors)

        expected_subjects = [s for s in dataset_meta.subjects if isinstance(s, str) and s.strip()]
        expected_subjects = [s.strip() for s in expected_subjects]
        if not expected_subjects:
            errors.append("dataset_meta.json: 'subjects' must be a non-empty list of subject IDs.")

        trial_sets_dir = root_dir / "trial_sets"
        actual_subject_dirs = sorted([p.name for p in trial_sets_dir.iterdir() if p.is_dir()]) if trial_sets_dir.exists() else []
        expected_sorted = sorted(expected_subjects)
        if actual_subject_dirs != expected_sorted:
            errors.append(
                "Bundle subject directories mismatch under 'trial_sets/'. "
                f"Expected: {expected_sorted} but found: {actual_subject_dirs}"
            )

        trials_by_subject: dict[str, list[Trial]] = {}
        for subject_id in expected_subjects:
            subject_errors = cls._validate_subject(
                root_dir,
                file_index=file_index,
                lower_to_actual=lower_to_actual,
                manifest=manifest,
                subject_id=subject_id,
                trials_by_subject=trials_by_subject,
            )
            errors.extend(subject_errors)

        manifest_errors = cls._validate_manifest_media(
            root_dir,
            file_index=file_index,
            lower_to_actual=lower_to_actual,
            manifest=manifest,
        )
        errors.extend(manifest_errors)

        if errors:
            raise BundleValidationError(errors)

        return cls(
            root_dir,
            dataset_meta=dataset_meta,
            manifest=manifest,
            file_index=file_index,
            lower_to_actual=lower_to_actual,
            trials_by_subject=trials_by_subject,
        )

    def validate_selected_subjects(self, subject_ids: list[str]) -> None:
        errors: list[str] = []
        for subject_id in subject_ids:
            if subject_id not in self._dataset_meta.subjects:
                errors.append(f"Selected subject '{subject_id}' is not listed in dataset_meta.json subjects.")
                continue
            subject_errors = self._validate_subject(
                self._root_dir,
                file_index=self._file_index,
                lower_to_actual=self._lower_to_actual,
                manifest=self._manifest,
                subject_id=subject_id,
                trials_by_subject=self._trials_by_subject,
            )
            errors.extend(subject_errors)
        if errors:
            raise BundleValidationError(errors)

    def load_trials(self, subject_id: str) -> list[Trial]:
        try:
            return list(self._trials_by_subject[subject_id])
        except KeyError as e:
            raise ValueError(f"No trial set loaded for subject '{subject_id}'.") from e

    def resolve_media_path(self, internal_path: str) -> Path:
        assert_safe_internal_path(internal_path)
        if not internal_path.startswith("media/"):
            raise ValueError(f"Not a bundle media path: '{internal_path}'")

        exact = self._file_index.get(internal_path)
        if exact is not None:
            return exact.resolve()

        lower = internal_path.lower()
        actual = self._lower_to_actual.get(lower)
        if actual is not None:
            raise FileNotFoundError(
                "Bundle media path case mismatch: "
                f"trial references '{internal_path}' but bundle contains '{actual}'"
            )

        raise FileNotFoundError(f"Bundle media missing: '{internal_path}'")

    @staticmethod
    def _require_directory(path: Path, errors: list[str], message: str) -> None:
        if not path.exists() or not path.is_dir():
            errors.append(message)

    @staticmethod
    def _build_file_index(root_dir: Path) -> tuple[dict[str, Path], dict[str, str], list[str]]:
        errors: list[str] = []
        file_index: dict[str, Path] = {}
        lower_to_actual: dict[str, str] = {}

        for p in root_dir.rglob("*"):
            if p.is_dir():
                continue
            try:
                rel = p.relative_to(root_dir).as_posix()
            except Exception:
                continue

            if not rel:
                errors.append(f"Invalid file with empty relative path: {p}")
                continue

            if "\\" in rel:
                errors.append(f"Invalid bundle file path contains backslash: '{rel}'")
                continue

            if rel in file_index:
                errors.append(f"Duplicate bundle file path detected: '{rel}'")
                continue

            lower = rel.lower()
            existing = lower_to_actual.get(lower)
            if existing is not None and existing != rel:
                errors.append(
                    "Bundle contains two files that differ only by case, which is not allowed: "
                    f"'{existing}' and '{rel}'"
                )
                continue

            file_index[rel] = p
            lower_to_actual[lower] = rel

        return file_index, lower_to_actual, errors

    @classmethod
    def _read_json_model(
        cls,
        root_dir: Path,
        *,
        file_index: dict[str, Path],
        lower_to_actual: dict[str, str],
        internal_path: str,
        model: type[BaseModel],
        errors: list[str],
    ) -> BaseModel | None:
        try:
            assert_safe_internal_path(internal_path)
        except Exception as e:
            errors.append(str(e))
            return None

        file_path = file_index.get(internal_path)
        if file_path is None:
            actual = lower_to_actual.get(internal_path.lower())
            if actual is not None:
                errors.append(
                    "Bundle file path case mismatch: "
                    f"expected '{internal_path}' but bundle contains '{actual}'"
                )
            else:
                errors.append(f"Bundle is missing required file at root: '{internal_path}'")
            return None

        try:
            raw = json.loads(file_path.read_text(encoding="utf-8"))
        except Exception as e:
            errors.append(f"Failed to parse JSON '{internal_path}': {e}")
            return None

        try:
            return model.model_validate(raw)
        except ValidationError as e:
            errors.append(f"Invalid '{internal_path}' schema: {e}")
            return None

    @classmethod
    def _validate_manifest_media(
        cls,
        root_dir: Path,
        *,
        file_index: dict[str, Path],
        lower_to_actual: dict[str, str],
        manifest: Manifest,
    ) -> list[str]:
        errors: list[str] = []
        for identity in manifest.identities:
            for exemplar in identity.image_exemplars:
                errors.extend(
                    cls._validate_media_reference(
                        root_dir,
                        file_index=file_index,
                        lower_to_actual=lower_to_actual,
                        internal_path=exemplar.relative_path,
                        context=f"manifest.json identity '{identity.id}' image exemplar index={exemplar.index}",
                        expected_prefix="media/images/",
                    )
                )
            for exemplar in identity.audio_exemplars:
                errors.extend(
                    cls._validate_media_reference(
                        root_dir,
                        file_index=file_index,
                        lower_to_actual=lower_to_actual,
                        internal_path=exemplar.relative_path,
                        context=f"manifest.json identity '{identity.id}' audio exemplar index={exemplar.index}",
                        expected_prefix="media/audio/",
                    )
                )
        return errors

    @classmethod
    def _validate_subject(
        cls,
        root_dir: Path,
        *,
        file_index: dict[str, Path],
        lower_to_actual: dict[str, str],
        manifest: Manifest,
        subject_id: str,
        trials_by_subject: dict[str, list[Trial]],
    ) -> list[str]:
        errors: list[str] = []

        trials_json_internal_path = f"trial_sets/{subject_id}/trials.json"
        try:
            assert_safe_internal_path(trials_json_internal_path)
        except Exception as e:
            errors.append(f"[{subject_id}] Invalid trials.json internal path: {e}")
            return errors

        trials_json_path = file_index.get(trials_json_internal_path)
        if trials_json_path is None:
            actual = lower_to_actual.get(trials_json_internal_path.lower())
            if actual is not None:
                errors.append(
                    f"[{subject_id}] trials.json path case mismatch: expected '{trials_json_internal_path}' "
                    f"but bundle contains '{actual}'"
                )
            else:
                errors.append(f"[{subject_id}] Missing required file: '{trials_json_internal_path}'")
            return errors

        try:
            raw = json.loads(trials_json_path.read_text(encoding="utf-8"))
        except Exception as e:
            errors.append(f"[{subject_id}] Failed to parse trials.json: {e}")
            return errors

        if not isinstance(raw, dict):
            errors.append(f"[{subject_id}] trials.json must be a JSON object.")
            return errors

        meta = raw.get("meta")
        if not isinstance(meta, dict):
            errors.append(f"[{subject_id}] trials.json: 'meta' must be a JSON object.")
            return errors

        meta_subject_id = str(meta.get("subjectId", "")).strip()
        if meta_subject_id != subject_id:
            errors.append(
                f"[{subject_id}] Trial set subject mismatch: folder '{subject_id}' but trials.json meta.subjectId "
                f"is '{meta_subject_id}'"
            )

        raw_trials = raw.get("trials")
        if not isinstance(raw_trials, list) or not raw_trials:
            errors.append(f"[{subject_id}] trials.json: 'trials' must be a non-empty array.")
            return errors

        parsed_trials: list[Trial] = []
        for i, rec in enumerate(raw_trials, start=1):
            try:
                trial = Trial.model_validate(rec)
            except ValidationError as e:
                errors.append(f"[{subject_id}] trials.json trial #{i} failed schema validation: {e}")
                continue

            if trial.subject_id != subject_id:
                errors.append(
                    f"[{subject_id}] Trial subject mismatch in trial_id='{trial.trial_id}': "
                    f"trial.subject_id='{trial.subject_id}'"
                )

            errors.extend(
                cls._validate_media_reference(
                    root_dir,
                    file_index=file_index,
                    lower_to_actual=lower_to_actual,
                    internal_path=trial.audio_path,
                    context=f"[{subject_id}] trial_id='{trial.trial_id}' audio",
                    expected_prefix="media/audio/",
                )
            )
            errors.extend(
                cls._validate_media_reference(
                    root_dir,
                    file_index=file_index,
                    lower_to_actual=lower_to_actual,
                    internal_path=trial.left_image_path,
                    context=f"[{subject_id}] trial_id='{trial.trial_id}' left_image",
                    expected_prefix="media/images/",
                )
            )
            errors.extend(
                cls._validate_media_reference(
                    root_dir,
                    file_index=file_index,
                    lower_to_actual=lower_to_actual,
                    internal_path=trial.right_image_path,
                    context=f"[{subject_id}] trial_id='{trial.trial_id}' right_image",
                    expected_prefix="media/images/",
                )
            )
            parsed_trials.append(trial)

        if errors:
            return errors

        trials_by_subject[subject_id] = sorted(parsed_trials, key=lambda t: t.trial_number)
        return errors

    @classmethod
    def _validate_media_reference(
        cls,
        root_dir: Path,
        *,
        file_index: dict[str, Path],
        lower_to_actual: dict[str, str],
        internal_path: str,
        context: str,
        expected_prefix: str,
    ) -> list[str]:
        errors: list[str] = []
        try:
            assert_safe_internal_path(internal_path)
        except Exception as e:
            errors.append(f"{context}: invalid path '{internal_path}': {e}")
            return errors

        if not internal_path.startswith(expected_prefix):
            errors.append(
                f"{context}: invalid media path prefix, expected '{expected_prefix}*' but got '{internal_path}'"
            )
            return errors

        exact = file_index.get(internal_path)
        if exact is None:
            actual = lower_to_actual.get(internal_path.lower())
            if actual is not None:
                errors.append(
                    f"{context}: path case mismatch, trial references '{internal_path}' but bundle contains '{actual}'"
                )
            else:
                errors.append(f"{context}: missing media file '{internal_path}'")
            return errors

        try:
            resolved = exact.resolve()
            root_resolved = root_dir.resolve()
            if not resolved.is_file():
                errors.append(f"{context}: media path is not a file: '{internal_path}'")
            if not resolved.is_relative_to(root_resolved):
                errors.append(f"{context}: media path escapes bundle root: '{internal_path}'")
        except Exception as e:
            errors.append(f"{context}: failed to resolve media path '{internal_path}': {e}")

        return errors
