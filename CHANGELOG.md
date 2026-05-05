# Changelog

## [0.3.16](https://github.com/CHiPmxbi/mxbiflow/compare/v0.3.15...v0.3.16) (2026-05-04)


### Features

* **models:** :sparkles: add initial/final stage serialization to Animal ([#89](https://github.com/CHiPmxbi/mxbiflow/issues/89)) ([7ed5e49](https://github.com/CHiPmxbi/mxbiflow/commit/7ed5e49a30c8751f487abd15f7ca3d7c7375ec43))

## [0.3.15](https://github.com/CHiPmxbi/mxbiflow/compare/v0.3.14...v0.3.15) (2026-04-14)


### Bug Fixes

* **deps:** remove pyaudio dependency ([351d065](https://github.com/CHiPmxbi/mxbiflow/commit/351d06531e9a0ced0a4640ca771355b8c7335a69))

## [0.3.14](https://github.com/CHiPmxbi/mxbiflow/compare/v0.3.13...v0.3.14) (2026-04-01)


### Bug Fixes

* **deps:** ⬆️ update dependency pymxbi to &gt;=0.3.7 ([#83](https://github.com/CHiPmxbi/mxbiflow/issues/83)) ([300d678](https://github.com/CHiPmxbi/mxbiflow/commit/300d678bf35def3dd2134c9ea786cd5e56aee6c9))
* improve detector fallback handling and pygame display lifecycle ([#81](https://github.com/CHiPmxbi/mxbiflow/issues/81)) ([ea70f82](https://github.com/CHiPmxbi/mxbiflow/commit/ea70f82bfe9bc0ea840ab6129b7d3fe7ceb56c46))

## [0.3.13](https://github.com/CHiPmxbi/mxbiflow/compare/v0.3.12...v0.3.13) (2026-03-31)


### Features

* **gameloop:** :sparkles: add configurable max fps at initialization ([#79](https://github.com/CHiPmxbi/mxbiflow/issues/79)) ([34c83aa](https://github.com/CHiPmxbi/mxbiflow/commit/34c83aa40c7fac99ccf6c3304e33e2a831c2b91b))


### Bug Fixes

* **deps:** ⬆️ update dependency pymxbi to &gt;=0.3.6 ([#75](https://github.com/CHiPmxbi/mxbiflow/issues/75)) ([f99c7bb](https://github.com/CHiPmxbi/mxbiflow/commit/f99c7bbfd97d25e3368ab54d913dd300baa51c1c))
* **scheduler:** :bug: route detector fallback events to configured scenes ([#76](https://github.com/CHiPmxbi/mxbiflow/issues/76)) ([81fdc13](https://github.com/CHiPmxbi/mxbiflow/commit/81fdc13c38d0d3e110743d03cd3198bcc862b21a))

## [0.3.12](https://github.com/CHiPmxbi/mxbiflow/compare/v0.3.11...v0.3.12) (2026-03-24)


### Bug Fixes

* **session:** :bug: fix daily rollover for session data directories ([#73](https://github.com/CHiPmxbi/mxbiflow/issues/73)) ([001a342](https://github.com/CHiPmxbi/mxbiflow/commit/001a342cdb87267801110c0320f90cfc022724c5))

## [0.3.11](https://github.com/CHiPmxbi/mxbiflow/compare/v0.3.10...v0.3.11) (2026-02-26)


### Features

* **report:** :sparkles: add shared image section renderer ([e26d834](https://github.com/CHiPmxbi/mxbiflow/commit/e26d83410f1a97dc3dc691b09368ffdb3eee4ce5))

## [0.3.10](https://github.com/CHiPmxbi/mxbiflow/compare/v0.3.9...v0.3.10) (2026-02-26)


### Bug Fixes

* **deps:** ⬆️ update dependency pymxbi to &gt;=0.3.5 ([#68](https://github.com/CHiPmxbi/mxbiflow/issues/68)) ([717e1a0](https://github.com/CHiPmxbi/mxbiflow/commit/717e1a0c572ea026a110b48ab6ceb1c8c1613404))

## [0.3.9](https://github.com/CHiPmxbi/mxbiflow/compare/v0.3.8...v0.3.9) (2026-02-26)


### Features

* **gameloop:** :sparkles: add screenshot capture hotkey ([#66](https://github.com/CHiPmxbi/mxbiflow/issues/66)) ([e88a820](https://github.com/CHiPmxbi/mxbiflow/commit/e88a820295c5c28d8b3e2a0adf7bb4dd0d36807e))

## [0.3.8](https://github.com/CHiPmxbi/mxbiflow/compare/v0.3.7...v0.3.8) (2026-02-19)


### Features

* **ui:** :sparkles: add send_email and sync_data checkboxes ([#64](https://github.com/CHiPmxbi/mxbiflow/issues/64)) ([f47fc60](https://github.com/CHiPmxbi/mxbiflow/commit/f47fc603fc39095a3f2fe9798bc9fcce450124da))


### Bug Fixes

* **deps:** ⬆️ update dependency pymxbi to &gt;=0.3.4 ([#55](https://github.com/CHiPmxbi/mxbiflow/issues/55)) ([b158ad0](https://github.com/CHiPmxbi/mxbiflow/commit/b158ad0094c3dc77fd840ad22bad8dbec73e40cf))
* **session:** :bug: allocate session_id only when session starts ([#65](https://github.com/CHiPmxbi/mxbiflow/issues/65)) ([7f90e72](https://github.com/CHiPmxbi/mxbiflow/commit/7f90e7297f49a99a760ec94a5e3844771d4b5544))
* **ui:** :bug: fix experimenter persistence in non-editable combobox ([#61](https://github.com/CHiPmxbi/mxbiflow/issues/61)) ([4d3cc78](https://github.com/CHiPmxbi/mxbiflow/commit/4d3cc7802e222b9d7d71ac7dc69f9f6642e52048))

## [0.3.7](https://github.com/CHiPmxbi/mxbiflow/compare/v0.3.6...v0.3.7) (2026-02-18)


### Features

* **session:** :sparkles: add email send state storage ([2cfadf9](https://github.com/CHiPmxbi/mxbiflow/commit/2cfadf9cef81736f191d56760f9f3c7eaa2cc39f))

## [0.3.6](https://github.com/CHiPmxbi/mxbiflow/compare/v0.3.5...v0.3.6) (2026-02-17)


### Features

* **infra:** :sparkles: add post-processing module for session summary ([#51](https://github.com/CHiPmxbi/mxbiflow/issues/51)) ([a91b78d](https://github.com/CHiPmxbi/mxbiflow/commit/a91b78d92fc459945ee23a33d2ccb951d2344960))

## [0.3.5](https://github.com/CHiPmxbi/mxbiflow/compare/v0.3.4...v0.3.5) (2026-02-17)


### Features

* **session:** :sparkles: add session configuration persistence ([#49](https://github.com/CHiPmxbi/mxbiflow/issues/49)) ([97c5723](https://github.com/CHiPmxbi/mxbiflow/commit/97c5723de69b2c7adfd0124dcd8217f6dda510c5))

## [0.3.4](https://github.com/CHiPmxbi/mxbiflow/compare/v0.3.3...v0.3.4) (2026-02-17)


### Bug Fixes

* **scene:** :art: rotate apple assets 90 degrees clockwise in idle scene ([#44](https://github.com/CHiPmxbi/mxbiflow/issues/44)) ([14f5eeb](https://github.com/CHiPmxbi/mxbiflow/commit/14f5eeb4fd4be30308f2b1bb81c66945baac8f75))

## [0.3.3](https://github.com/CHiPmxbi/mxbiflow/compare/v0.3.2...v0.3.3) (2026-02-17)


### Features

* **ui:** :sparkles: add auto-accept countdown timer to config panels ([#43](https://github.com/CHiPmxbi/mxbiflow/issues/43)) ([a0e479d](https://github.com/CHiPmxbi/mxbiflow/commit/a0e479d793270244902575a4856a9657c9ac68b9))


### Bug Fixes

* **deps:** ⬆️ update dependency pymxbi to &gt;=0.3.1 ([#32](https://github.com/CHiPmxbi/mxbiflow/issues/32)) ([f41aa2e](https://github.com/CHiPmxbi/mxbiflow/commit/f41aa2e6453b56e9a58837fa8e32a2474c9e5491))
* **deps:** ⬆️ update dependency pymxbi to &gt;=0.3.2 ([#34](https://github.com/CHiPmxbi/mxbiflow/issues/34)) ([9cd3f7f](https://github.com/CHiPmxbi/mxbiflow/commit/9cd3f7fbe82799947d31164117d2eb0667499d00))
* **deps:** ⬆️ update dependency pymxbi to &gt;=0.3.3 ([#42](https://github.com/CHiPmxbi/mxbiflow/issues/42)) ([e3a4c2b](https://github.com/CHiPmxbi/mxbiflow/commit/e3a4c2bacc0a6adc22bd823b54a90ff224451efa))
* **ui:** :bug: remove unnecessary str() conversion for mxbi_id ([#40](https://github.com/CHiPmxbi/mxbiflow/issues/40)) ([e966ce3](https://github.com/CHiPmxbi/mxbiflow/commit/e966ce3c906eb0d88cbf305fb093a3733fe76e42))

## [0.3.2](https://github.com/CHiPmxbi/mxbiflow/compare/v0.3.1...v0.3.2) (2026-02-17)


### Bug Fixes

* **renovate:** add bump rangeStrategy for pymxbi ([#30](https://github.com/CHiPmxbi/mxbiflow/issues/30)) ([5745e04](https://github.com/CHiPmxbi/mxbiflow/commit/5745e0419c57925ca904b736545a379af5981bf5))

## [0.3.1](https://github.com/CHiPmxbi/mxbiflow/compare/v0.3.0...v0.3.1) (2026-02-17)


### Features

* 🎨 add gitmoji support in renovate config ([8998c99](https://github.com/CHiPmxbi/mxbiflow/commit/8998c999aa419957d9fbeb667c843251917ecc9d))


### Bug Fixes

* **ci:** use config-file instead of release-type for release-please ([#28](https://github.com/CHiPmxbi/mxbiflow/issues/28)) ([abcf545](https://github.com/CHiPmxbi/mxbiflow/commit/abcf54520d7d9b93351fd3be9e66417bcab2a3b3))

## [0.3.0](https://github.com/CHiPmxbi/mxbiflow/compare/v0.2.0...v0.3.0) (2026-02-13)


### Features

* **ui:** 🎨 add fullscreen and hide cursor options to session config ([19df3c2](https://github.com/CHiPmxbi/mxbiflow/commit/19df3c2d5b845c4431c90c451603abcfe132b081))


### Bug Fixes

* **ui:** optimize column stretch in devices layout ([2731637](https://github.com/CHiPmxbi/mxbiflow/commit/27316370707096983cce12e538c1b2791030691d))

## [0.2.0](https://github.com/CHiPmxbi/mxbiflow/compare/v0.1.10...v0.2.0) (2026-02-13)


### Features

* **ui:** 🔥 remove platform selection from BaseConfig ([#21](https://github.com/CHiPmxbi/mxbiflow/issues/21)) ([dad8906](https://github.com/CHiPmxbi/mxbiflow/commit/dad89066e5e173e3e912c21ecc69d2304f7e3e6b))

## [0.1.10](https://github.com/CHiPmxbi/mxbiflow/compare/v0.1.9...v0.1.10) (2026-02-13)


### Bug Fixes

* **detector:** 🐛 add mxbi initialization and cleanup in Game class ([#19](https://github.com/CHiPmxbi/mxbiflow/issues/19)) ([6be6d72](https://github.com/CHiPmxbi/mxbiflow/commit/6be6d72948942d807070fcb5cb68354f339242bd))
