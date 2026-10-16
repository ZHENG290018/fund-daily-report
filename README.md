# 基金每日战报（GitHub Pages + Actions）

页面托管在 GitHub Pages，持仓配置放在 `holdings.json`，GitHub Actions 每个交易日晚上 22:00（北京时间）自动抓取天天基金净值、计算当日收益，并通过 Server酱 把战报推送到微信。

```
├── index.html                      # 工作台页面（GitHub Pages 托管）
├── holdings.json                   # 持仓配置（网页与定时推送共用）
├── scripts/daily_push.py           # 每日战报脚本
└── .github/workflows/daily-push.yml
```

## 部署步骤（约 5 分钟）

1. **创建仓库并上传**：在 GitHub 新建一个仓库（如 `fund-daily-report`，Public 才能免费用 Pages），然后：

   ```bash
   cd fund-daily-report
   git remote remove origin 2>/dev/null
   git remote add origin https://github.com/<你的用户名>/fund-daily-report.git
   git push -u origin main
   ```

2. **配置推送密钥**：仓库页 → Settings → Secrets and variables → Actions → New repository secret
   - Name：`SCT_SENDKEY`
   - Value：你的 Server酱 SendKey（在 [sct.ftqq.com](https://sct.ftqq.com) 用微信扫码登录即可免费获取）

3. **开启 GitHub Pages**：Settings → Pages → Source 选 `Deploy from a branch`，分支选 `main` / `(root)`，保存。
   稍等 1~2 分钟，页面地址就是 `https://<你的用户名>.github.io/fund-daily-report/`。

4. **替换持仓**（重要！）：`holdings.json` 里现在是示例数据，两种方式换成你自己的：
   - 打开旧页面（fund-daily-profit.app.workbuddy.host）→ 点「导出持仓」→ 用下载的 `holdings.json` 覆盖仓库里的同名文件，commit；
   - 或直接手动编辑：每只基金 `{"code": "基金代码", "shares": 持有份额, "cost": 成本单价}`。
   持仓变了就改这个文件提交，推送和网页会一起更新。

5. **测试**：仓库页 → Actions → 「基金每日战报」→ Run workflow 手动跑一次。没配 SendKey 时会只在日志里打印战报（dry run），方便先看效果。

## 说明

- **推送时间**：默认北京时间每周一至五 22:00（UTC cron `0 14 * * 1-5`）。多数基金净值 19:00~21:00 公布，22:00 推基本是最终值；想更晚可把 cron 改成 `30 14 * * 1-5`（22:30）等。
- **节假日**：所有基金净值都不是当日时自动跳过推送，法定节假日不会误报（周末 cron 本身不触发）。
- **GitHub 定时任务有延迟**：cron 触发可能有 0~30 分钟偏差，属正常现象。
- **定时任务休眠**：公共仓库 60 天没有任何提交时，GitHub 会暂停 schedule，仓库页会收到邮件提醒，重新启用或在 Actions 里手动跑一次即可。
- **网页数据同步**：网页版数据仍存浏览器 localStorage；首次打开会自动读取仓库里的 `holdings.json` 作为初始持仓。改了浏览器里的持仓后，用「导出持仓」下载文件覆盖仓库里的 `holdings.json` 即可让推送口径保持一致。
