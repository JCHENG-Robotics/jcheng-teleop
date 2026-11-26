# Changelog

All notable changes to this project are documented here. Format based on
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/); this project follows
[Semantic Versioning](https://semver.org/).

## [Unreleased]

## [0.1.0] — 2026-11-26

### Added

- Initial repository scaffold: bilingual documentation set, admission manifest,
  repository gate, no-device static scan and `teleop-gate` CI.
- L3 admission for teleoperation intent: `safety.class: offline`,
  `hardware_access: none` and an empty runtime surface. The reserved
  `TeleopCommand` stream from `jcheng-interfaces` v0.1.0 is referenced but not
  published.
- Input, intent and integration boundary documents for the planned ROS-free
  core (M1) and intent node (M2).
