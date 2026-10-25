"""UT Austin courses and the shorthand students actually type (FR-18, FR-19)."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Course:
    code: str
    title: str
    subject: str


_COURSES = [
    Course("CH 301", "Principles of Chemistry I", "chemistry"),
    Course("CH 302", "Principles of Chemistry II", "chemistry"),
    Course("CH 320M", "Organic Chemistry I", "chemistry"),
    Course("CH 320N", "Organic Chemistry II", "chemistry"),
    Course("CH 369", "Fundamentals of Biochemistry", "chemistry"),
    Course("M 408C", "Differential and Integral Calculus", "mathematics"),
    Course("M 408D", "Sequences, Series, and Multivariable Calculus", "mathematics"),
    Course("M 427J", "Differential Equations with Linear Algebra", "mathematics"),
    Course("M 340L", "Matrices and Matrix Calculations", "mathematics"),
    Course("M 362K", "Probability I", "mathematics"),
    Course("C S 312", "Introduction to Programming", "computer science"),
    Course("C S 314", "Data Structures", "computer science"),
    Course("C S 311", "Discrete Math for Computer Science", "computer science"),
    Course("C S 429", "Computer Organization and Architecture", "computer science"),
    Course("C S 439", "Principles of Computer Systems", "computer science"),
    Course("C S 331", "Algorithms and Complexity", "computer science"),
    Course("PHY 303K", "Engineering Physics I", "physics"),
    Course("PHY 303L", "Engineering Physics II", "physics"),
    Course("BIO 311C", "Introductory Biology I", "biology"),
    Course("BIO 311D", "Introductory Biology II", "biology"),
    Course("ECO 304K", "Introduction to Microeconomics", "economics"),
    Course("ECO 304L", "Introduction to Macroeconomics", "economics"),
    Course("STA 309", "Elementary Biostatistics", "statistics"),
    Course("PSY 301", "Introduction to Psychology", "psychology"),
]

COURSES: dict[str, Course] = {c.code: c for c in _COURSES}

# Department spellings students type → catalog department prefix.
DEPARTMENTS: dict[str, str] = {
    "ch": "CH",
    "chem": "CH",
    "m": "M",
    "math": "M",
    "cs": "C S",
    "c s": "C S",
    "phy": "PHY",
    "phys": "PHY",
    "bio": "BIO",
    "eco": "ECO",
    "econ": "ECO",
    "sta": "STA",
    "stat": "STA",
    "psy": "PSY",
    "psych": "PSY",
}

DEPARTMENT_SUBJECT: dict[str, str] = {
    "CH": "chemistry",
    "M": "mathematics",
    "C S": "computer science",
    "PHY": "physics",
    "BIO": "biology",
    "ECO": "economics",
    "STA": "statistics",
    "PSY": "psychology",
}

# Multi-word shorthand → course. Checked before single keywords; longest phrase wins.
COURSE_ALIASES: dict[str, str] = {
    "orgo 1": "CH 320M",
    "orgo i": "CH 320M",
    "ochem 1": "CH 320M",
    "organic chemistry 1": "CH 320M",
    "organic chemistry i": "CH 320M",
    "orgo 2": "CH 320N",
    "orgo ii": "CH 320N",
    "ochem 2": "CH 320N",
    "organic chemistry 2": "CH 320N",
    "gen chem 1": "CH 301",
    "gen chem 2": "CH 302",
    "calc 1": "M 408C",
    "calc i": "M 408C",
    "calc 2": "M 408D",
    "calc ii": "M 408D",
    "linear algebra": "M 340L",
    "diff eq": "M 427J",
    "data structures": "C S 314",
    "discrete math": "C S 311",
    "intro bio": "BIO 311C",
    "micro econ": "ECO 304K",
    "microeconomics": "ECO 304K",
    "macroeconomics": "ECO 304L",
}

# Single keywords → course when unambiguous, else only a subject.
KEYWORD_COURSE: dict[str, str] = {
    "orgo": "CH 320M",
    "ochem": "CH 320M",
    "stereochem": "CH 320M",
    "stereochemistry": "CH 320M",
}

KEYWORD_SUBJECT: dict[str, str] = {
    "chem": "chemistry",
    "chemistry": "chemistry",
    "stoichiometry": "chemistry",
    "mechanisms": "chemistry",
    "titration": "chemistry",
    "calc": "mathematics",
    "calculus": "mathematics",
    "derivatives": "mathematics",
    "integrals": "mathematics",
    "matrices": "mathematics",
    "probability": "mathematics",
    "trees": "computer science",
    "graphs": "computer science",
    "recursion": "computer science",
    "algorithms": "computer science",
    "java": "computer science",
    "pointers": "computer science",
    "physics": "physics",
    "kinematics": "physics",
    "circuits": "physics",
    "biology": "biology",
    "genetics": "biology",
    "cells": "biology",
    "econ": "economics",
    "economics": "economics",
    "stats": "statistics",
    "statistics": "statistics",
    "regression": "statistics",
    "psych": "psychology",
    "psychology": "psychology",
}

SUBJECTS: tuple[str, ...] = tuple(sorted(set(DEPARTMENT_SUBJECT.values())))
GENERAL_SUBJECT = "general"


def course_by_number(number: str) -> Course | None:
    """A bare course number ("314") resolves only when exactly one catalog course has it."""
    hits = [c for c in _COURSES if c.code.rsplit(" ", 1)[1] == number.upper()]
    return hits[0] if len(hits) == 1 else None
