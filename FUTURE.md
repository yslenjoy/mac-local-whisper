P0
- [ ] 直接插入外部软件（非终端）权限
- [x] 稳定性（2026-04-01）：转写移至主线程通过 queue 执行，避免 daemon thread 调用 torch/C 扩展导致 segfault 及 semaphore 泄漏
  ```
  ● 录音中...
  ● 录音中...
  ◎ 转写中...
  zsh: segmentation fault  /Library/Developer/CommandLineTools/usr/bin/python3 
  (base) yslenjoy@vpnduopool-10-251-160-72 Downloads % 6
  zsh: command not found: 6
  (base) yslenjoy@vpnduopool-10-251-160-72 Downloads % 
  (base) yslenjoy@vpnduopool-10-251-160-72 Downloads % No it, when I say it/Library/Developer/CommandLineTools/Library/Frameworks/Python3.framework/Versions/3.9/lib/python3.9/multiprocessing/resource_tracker.py:216: UserWarning: resource_tracker: There appear to be 1 leaked semaphore objects to clean up at shutdown
  warnings.warn('resource_tracker: There appear to be %d '
  ```
- [x] 标点（2026-04-01）
  - [x] 末尾不要句号
  - [x] 用中文逗号而不是英文的

- [x] 句间标点（2026-04-01）：末尾句号替换为空格，连续录音粘贴后句子之间有自然间隔
- [ ] 架构：post-processing 规则（标点替换、末尾去句号等）硬编码在主流程里，应拆到独立模块/配置，和 pipeline 解耦，方便扩展自定义规则

P1
- [x] 改成mlx-whisper（2026-04-01）：BACKEND=mlx, MODEL_NAME=large-v3，补 initial_prompt
- [x] 长句识别不准（2026-04-01）：模型大小问题，medium → large；后续切 mlx-whisper 后速度可跟上
  
P2
- [ ] 流式输出
- [ ] post-processing 规则与 Whisper initial_prompt 融合：探索把标点/格式规则直接通过 prompt 引导模型输出，而不是事后字符串替换，两者职责更清晰