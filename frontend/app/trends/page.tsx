"use client";

import { useEffect } from "react";

// v7 W3: /trends 已下线, 趋势/爬虫能力迁移到决策结果的「📎 展开更多」信息流.
export default function TrendsPage() {
  useEffect(() => {
    window.location.replace("/");
  }, []);
  return null;
}
