\
# Goal: Fix flaky login

## Project

example-app

## Objective

Fix the intermittent login failure and add regression coverage.

## Scope

- reproduce the issue
- identify root cause
- implement minimal fix
- add regression test

## Out of scope

- auth provider migration
- permission model redesign
- unrelated UI refactor

## Acceptance

- test reproduces previous failure
- fix passes targeted and existing auth tests
- no breaking API change
