# 封面陈列室

这里保存每次封面改版的历史版本。

规则：

- `05_exports/YYYY-MM-DD/` 只保留当前最终发布封面。
- `15_cover_gallery/YYYY-MM-DD/` 保存所有改版底稿。
- `15_cover_gallery/INDEX.md` 是总索引，由 `npm run cover:gallery` 重建。
- 每次改版后运行 `npm run archive-cover -- YYYY-MM-DD --source 05_exports/YYYY-MM-DD/YYYY-MM-DD_DayNN_cover.jpg --title "当天主题" --note "版本说明"`。
- 每个日期目录里的 `INDEX.md` 记录版本、文件、主题和说明。
