"""Persistence boundaries for the new application core."""

from .assessments import AssessmentSubmissionRepository, MongoAssessmentSubmissionRepository
from .adaptive import AdaptiveLearningRepository, MongoAdaptiveLearningRepository

__all__ = [
    "AdaptiveLearningRepository",
    "AssessmentSubmissionRepository",
    "MongoAdaptiveLearningRepository",
    "MongoAssessmentSubmissionRepository",
]
