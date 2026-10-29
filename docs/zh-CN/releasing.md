# 发布流程

给维护者看。一次发布是打在某个提交上的注解 tag `vX.Y.Z`，该提交的三个版本文件必须
一致；其余由 `.github/workflows/release.yml` 完成。本页没有任何东西需要从上一次发布
记下来：检查都在 `tools/release.py` 和 workflow 里。

## 打 tag 之前

有三个手写文件携带版本号，而它们是在不同时刻写的——这就是它们会漂移的原因：

| 文件 | 必须写着 |
| --- | --- |
| `src/kernlens/__init__.py` | `__version__ = "X.Y.Z"` |
| `CHANGELOG.md` | `## [X.Y.Z] - YYYY-MM-DD`，且至少有一条记录 |
| `CITATION.cff` | `version: X.Y.Z` 以及与之一致的 `date-released` |

`tools/release.py check` 比对这三处，若给了 tag 也一并比对：

```console
uv sync --group release
uv run python tools/release.py check v0.3.0rc2
uv run pytest -q
rm -rf dist && uv build
uv run python tools/check_wheel.py dist/*.whl
uv run twine check dist/*
```

这个检查在 tag 存在之前就跑，这正是重点：tag 在推送之前改起来便宜，推送之后很贵。
`twine check` 会按 PyPI 的方式渲染 README，所以元数据错误在这里被发现，而不是在一次
被拒绝的上传里。

有两项只在给了 tag 时才检查，因为这道闸门也在普通分支上跑：tag 必须等于
`__version__`，且 changelog 里的 `[Unreleased]` 必须为空。留在发布提交
`Unreleased` 下面的条目，就是发布说明不会提到的条目。

## 预发布版本（rc）

版本号可以是 `X.Y.ZrcN`（如 `0.3.0rc2`），即预发布。写法与普通版本完全一样——
同样三个文件、同样的 changelog 小节、tag `v0.3.0rc2`——只有两点不同：

- **GitHub Release 会带上 `--prerelease` 标记**，因此不会成为仓库的 latest
  release。这个判断由 `tools/release.py prerelease` 做出，用的是 `check` 的同一个
  正则，所以两者不可能互相矛盾。
- **只有在没有别的版本可选时，安装器才会装它。** pip 确实会装 rc，但仅限于
  它是满足要求的最高版本：当 `0.3.0rc2` 是唯一的上传时，
  `pip install kernlens` 会解析到它。一旦存在正式版，rc 就不再是候选——
  `pip install kernlens` 会拿 `0.3.0`，rc 只能靠点名
  （`kernlens==0.3.0rc2`）或 `--pre` 才装得上。这段结论是 2026-10-30 对
  TestPyPI 实测得出的，而不是推断的：本段初稿写的是「必须加 `--pre`」，那是错的。

PyPI 仍然拒绝同一个版本上传两次，所以 rc 与正式版一样是永久的。

发布前值得先跑一次演练，即使三个版本文件全部通过：它是唯一可能因为仓库
之外的原因而失败的一步。未注册信任发布者时，报错是

```text
invalid-publisher: valid token, but no corresponding publisher
```

下面会打印它尝试过的 claims -- `sub`、`repository_owner`、
`workflow_ref`、`environment`。这些 claim 就是 PyPI
*Add a publisher* 表单里要填的值，所以这次失败本身就是填法说明。它失败在
`publish` 任务，此时 `build` 已经通过，且没有任何上传；改好发布者后重跑
同一个版本即可。

## 打 tag

```console
git tag -a v0.3.0rc2 -m "KernLens 0.3.0rc2"
git push origin v0.3.0rc2
```

要注解 tag，不要轻量 tag：`git describe`、`gh release` 和 workflow 的
`github.ref_name` 都读注解，而轻量 tag 很容易不小心打到错误的提交上。

## workflow 做什么

1. checkout 该 tag，同步 `release` 依赖组（twine）；
2. 带着 tag 运行 `tools/release.py check`，不一致就在这里停下；
3. 跑测试套件，因为 tag 可能指向一个 CI 从未见过的提交；
4. 构建 wheel 与 sdist，检查 wheel 内容和元数据；
5. 从 changelog 的那一节渲染发布说明；
6. 通过 trusted publishing 发布到 PyPI；
7. 用 wheel、sdist、演示 cast 和那份说明创建 GitHub Release。

先发 PyPI 再建 GitHub Release 是有意的。一个指向上传失败产物的发布，比一个还没有发布
的包更糟；反过来失败则是：包已存在，而发布可以手动补建。

## 一次性配置

首次上传之前，PyPI 必须先信任本仓库。在项目页：*Publishing* → *Add a publisher* →
GitHub，填

| 字段 | 值 |
| --- | --- |
| Owner | `BinRacer` |
| Repository | `KernLens` |
| Workflow | `release.yml` |
| Environment | `pypi` |

TestPyPI 是同样的表单，环境填 `testpypi`。任何地方都不存 token：job 里的
`id-token: write` 就是全部凭据。

预演是一次手动运行，它把**当前**版本发到 TestPyPI 然后停下：

```console
gh workflow run release.yml -f index=testpypi
```

TestPyPI 也不接受同一个版本第二次，所以一个版本只能预演一次。如果预演有问题，抬高
patch 版本，而不是重新上传。

## 出问题了怎么办

- **tag 打错了，什么都没发出去。** 在本地和远端删掉 tag，修好提交，重新打。PyPI
  从未被触碰。
- **PyPI 收下了这个版本，但内容是错的。** 版本号不能被替换。把它 yank 掉——文件仍可
  下载，依赖解析会跳过它们——修好，再发一个 patch。
- **workflow 在 PyPI 那一步之后失败。** 用 workflow 的产物手动创建 GitHub Release；
  包已经上线了。
- **GitHub Release 写错了。** 直接编辑。它是一个页面，不是产物仓库。

## 发布之后

- **安装命令变得合法了。** 两份 README 在发布存在之前刻意不提供
  `pip install kernlens`；`tests/unit/test_structure.py` 持有那份短语清单。在同一个
  提交里删掉那些条目并加上命令——那个测试是绊线，不是风格规定。
- **文档 URL 变成真的了。** 在首次 Pages 部署之后再加 `[project.urls]
  Documentation` 和 README 徽章，而不是之前；在那之前它们指向 404。
- **可以申请 DOI 了。** 在 Zenodo 上连接本仓库，切出下一个发布，然后把 DOI 写进
  `CITATION.cff` 和 README。版本 DOI 之后无法更改，所以值得等一个你满意的发布。
- **可以将一行升级了。** 如果有人在 [`compatibility.md`](../compatibility.md) 里标为
  "预期"的环境上跑过发布，那一行可以变成"实测"——附上 `kernlens doctor` 的输出作为
  证据。

## 没有自动化的部分

- **名称可用性。** 首次上传前检查 `https://pypi.org/pypi/kernlens/json`。它在
  2026-10-28 返回 404，这正是该名称可用的原因；如果这一点变了，发行包名也要跟着改。
- **仓库 topics 与社交预览图。** 预览图 GitHub 没有 API，topics 是界面操作。
- **捕获。** 换内核意味着要先重新生成 `tools/tutorial_capture.json`，否则教程和演示
  会一直在描述旧内核。

---