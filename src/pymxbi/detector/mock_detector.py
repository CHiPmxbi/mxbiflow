'''
Author: HuYang huyangcommit@gmail.com
Date: 2026-01-05 22:13:50
LastEditors: HuYang huyangcommit@gmail.com
LastEditTime: 2026-01-13 01:21:47
Description: 

Copyright (c) 2026 by HuYang huyangcommit@gmail.com, All Rights Reserved. 
'''
from pymxbi.detector.detector import Detector

class MockDetector(Detector):
    def __init__(self) -> None:
        super().__init__()

    def _begin(self) -> None:
        ...

    def _quit(self) -> None:
        ...
