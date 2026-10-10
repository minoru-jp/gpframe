<!--
この文書は `shikumi-devdoc` によって生成された canonical document です。
Canonical source は `devdocs/canonical_sources/status/canonical.py` です。
直接編集しないでください。

公開文書作成方針

- `devdocs/canonical_documents/` にある日本語 canonical document を公開工程の入力とする。
- 翻訳では意味、構造、情報量を維持し、内容を勝手に追加・削除・要約しない。
- canonical document に `shikumi-devdoc:translation-metadata` が含まれる場合は、その `preserve_spelling` 指定の用語の表記を変更しない。
- コード、Python 識別子、コマンド、ファイルパス、URL は、翻訳上の必要がない限り変更しない。
- このコメントブロックは published document には含めない。
- published document は canonical document から派生する公開成果物として扱い、内容の変更が必要な場合は canonical source または realization context へ戻して canonical document を再生成する。
-->

# gpframe Project Status

`gpframe` の現在の状態と、現在から見た今後の方向を記述する。
過去に実際に起きた変更は CHANGELOG が担当する。

## STATUS_001

現在の開発段階は Alpha。現在のバージョンは `0.1.0` で、PyPI にはまだ公開していない。PyPI 上の最新は作り直す前の旧実装 `0.0.34` である。

title: Development stage

## STATUS_002

対象の Python バージョン範囲は `>=3.11`。`SessionFailed` が標準の `ExceptionGroup` を使い、`spawn()` の型付けが `TypeVarTuple` を使うためである。実行時の依存パッケージはない。

title: Supported Python

## STATUS_003

実行はスレッド(同期版の `gpframe`)と、asyncio のタスク(非同期版の `gpframe.aio`)を扱う。プロセスは扱わない。同期版で提供している機能は次のとおり。

- `gpframe.session()` で開くセッションと、`spawn()` で起動するフレーム。停止の後の `spawn()` は、ルーティンを呼ばない stopped のフレームを返す
- 失敗したフレームの承認(`ignore()` / `escalate()`)と、セッション終了時の判定
- 協調的な停止(`stop()` / `ctx.stopping` / `ctx.wait_stop()`)と、止まらなかったフレームの報告
- ブロックする処理を止めるための停止コールバック(`ctx.on_stop()`)
- 最初の失敗を待つ `wait_broken()`。`idle=True` で、フレームが増減するセッションの失敗を待ち続けられる
- 終わり方を問わずフレームの終わりを待つ `Frame.wait()`
- 終わったフレーム(succeeded、stopped、`ignore()` 済み)とその引数を手放すこと。長く開いたセッションでもメモリが溜まらない
- フレームの中のサブセッションと、不完全なサブセッションの親フレームへの報告
- 型の固定された共有セル `Shared`
- フレーム間で値を順に受け渡し、送受信の待ちが停止で解ける `Channel`。容量の上限(`maxsize`)を付けると、送る側は空きを待つ

同期版で `async def` のルーティンを使うと、フレームのスレッド内の専用イベントループで動く。停止の確認は `ctx.stopping` のポーリングになる。

title: Scope

## STATUS_004

振る舞いの規則は Specification を正本とする。同期版は `devdocs/canonical_sources/specification/`、非同期版は `devdocs/canonical_sources/specification_aio/` に置く。そのうちテストで守る約束を `shikumi-contrace` の契約として `contract/` に置き、公開 API の形は `contract/ports/` に Protocol として置いている(同期版は `surface.py`、非同期版は `aio_surface.py`)。契約は同期版が 6 つ(`SessionContract`、`FrameContract`、`ContextContract`、`StopHandleContract`、`SharedContract`、`ChannelContract`)、非同期版が 5 つ(`AsyncSessionContract`、`AsyncFrameContract`、`AsyncContextContract`、`AsyncStopHandleContract`、`LoopMonitorContract`)である。

pytest で次の三つを確かめている。すべての条項に少なくとも一つのテストが結びついていること。すべての条項が `source` で根拠となる仕様の規則を指していること。指された規則が仕様書に実在すること。

pytest は `--contrace-check` を常に付けて実行し、警告をすべてエラーとして扱う。そのため契約資産の構造上の問題や、承認されていない失敗の警告があれば、テストは失敗する。

title: Contracts and tests

## STATUS_009

検査はすべて `tools/check.py` にまとめている。`docs`(canonical document と公開文書が最新であること)、`format`、`lint`、`types`、`types-tests`、`tests`、`dist`(sdist と wheel を作り、`twine check --strict`、中身の検査、依存のないきれいな venv での動作確認)の七つで、`python tools/check.py` ですべてを、名前を並べれば一部を走らせる。検査に使う道具の版は、`pyproject.toml` の extras(`dev` がすべてを含む)で固定している。

GitHub Actions は二つのワークフローからなる。

- `ci.yml`: プッシュとプルリクエストのたびに、Python 3.11、3.12、3.13 で `python tools/check.py` を走らせる。
- `release.yml`: GitHub で Release を公開すると、まず `ci.yml` をそのまま呼んで同じ検査を通す。そのうえで `python tools/check.py dist --tag <タグ>` で配布物を作って確かめ(タグが `v<version>` と一致することも確かめる)、PyPI の Trusted Publishing で公開する。API トークンは使わない。

Trusted Publishing のため、PyPI 側でこのリポジトリ、ワークフロー `release.yml`、環境 `pypi` を Trusted Publisher として登録しておく必要がある。

title: Checks, CI and release

## STATUS_010

英語の公開文書は、日本語の canonical document を翻訳して作る。README、STATUS、CHANGELOG はリポジトリのルートに、Specification は `docs/specification/` と `docs/specification_aio/` に置く。翻訳そのものは自動化しておらず、`scripts/published_docs.py` が次のことを機械で確かめる(`tools/check.py docs` に含まれる)。

- すべての canonical document に公開文書があり、余分な公開文書がないこと
- 公開文書の先頭の印が、いまの canonical document の SHA-256 と一致すること。canonical document が変われば、翻訳し直して `python scripts/published_docs.py stamp <公開文書>` で印を付け直すまで検査は失敗する
- Python のコード例が、コメントと docstring を除いて canonical document と同じであること
- 仕様の規則の見出しが、同じ順に同じだけあること
- リンクの先が実在すること

title: Published documents

## STATUS_005

静的解析は `ruff format --check .`、`ruff check .`、BasedPyright の二つの設定がいずれも clean。

- Ruff は 0.16.10 を固定し、Python 3.11 を target version とする。lint は固定版の既定の規則集合を基準にする。
- BasedPyright 1.40.2 で、`src/gpframe`、`contract/ports`、`tools`、`examples` を `recommended` mode で検査し、0 errors / 0 warnings。無効にしている診断は二つだけで、`reportImplicitOverride` は `typing.override` が Python 3.12 からのため、`reportPrivateUsage` は先頭の `_` を package 外への公開境界として扱い、同じモジュール内のセッション・フレーム・コンテキストが互いの内部状態を扱うためである。
- `tests/pyrightconfig.json` で、テスト、契約、文書の正本を利用側として `standard` mode で検査し、0 errors / 0 warnings。

実行時の意味を保つために必要な局所的な抑制(`pyright: ignore` と `noqa`)には、理由を隣に書いている。

title: Static analysis

## STATUS_006

テストの `@binds[Subject](Implementation)` は、実装が公開 API の Protocol を満たすことを型検査で確かめる役割も持つ。ただし BasedPyright 1.40.2 では、`binds` の引数の型 `T | Callable[..., T]` に対して、クラスオブジェクトと Protocol を比べた途中結果を誤って再利用し、互いに参照し合う `Context` と `Session` の適合を失敗と判定することがある。

回避のため、`binds` を使うテストモジュールの先頭で、実装を `Callable[..., Protocol]` 型の変数に代入して形を先に確かめている。実装をわざと壊すとこの確認と `binds` の両方がエラーを出すことは確認済みである。

title: Known type-checker behavior

## STATUS_007

非同期版 `gpframe.aio` は、イベントループの上でフレームをタスクとして動かす。同期版とは型を共有しない独立した API で、停止はタスクのキャンセルで行う。停止の要求で終わったフレームは stopped になり、失敗として扱わない。

- `aio.session()` で開くセッションと `spawn()`(コルーチン関数のみ)、`await` による待機(`wait()`、`wait_broken()`、`AsyncFrame.result()`)
- 失敗の承認と、終了時の判定。所有タスク自身がキャンセルされた場合は、キャンセルを優先して失敗を警告で報告する
- キャンセルでは止まらない処理のための停止コールバック(`ctx.on_stop()`)
- フレームの中のサブセッション
- ループの停滞を、ループの外のスレッドから検出して報告するヘルスチェック `aio.monitor()`

非同期版の仕様は「Constraints and limits」の文書から始まる。ループをブロックしたフレームに対しては `timeout` や報告の保証が失われること、キャンセルを無視するタスクは切り離して後始末を保証しないことを、設計の不足ではなく原理的な限界として表明している。

title: Async API

related: [ALIMIT_001](../specification_aio/limits.md#alimit_001), [ALIMIT_002](../specification_aio/limits.md#alimit_002)

## STATUS_008

gpframe 自身の開発に、gpframe で作った道具を使っている(ドッグフーディング)。`tools/devwatch.py` は、ファイルの変更を検知するワーカー、文書の生成と検査を走らせるワーカー(検査ごとのサブセッションを持つ)、生成した文書を配信するワーカーからなるワーカーの木で、公開 API だけを使って書いている。`python tools/devwatch.py --once` は、文書を生成したうえで、CI と同じ `tools/check.py` の検査(`dist` を除く)を並行に走らせる。

この道具を書いたことで、停止の後の `spawn()` が普通の停止を失敗に変えてしまう問題と、ワーカー間の受け渡しの待ちを停止で解く手段がない問題が見つかり、それぞれ stopped のフレームと `Channel` で解決した。

非同期版は `examples/chat.py` で試している。接続ごとにフレームを起動する行単位のチャットサーバーで、接続ごとの失敗を受け付けの階層で `ignore()` し、全体をヘルスチェックの中で動かす。この例で、終わったフレームがセッションに溜まり続けること(4000 接続で約 18MB)、実行中のフレームがないと `wait_broken()` が待てないこと、終わり方を問わずにフレームの終わりを待つ手段がないことが見つかり、それぞれフレームの手放し、`idle=True`、`wait()` で解決した。

`Channel` は `examples/logstats.py` で試している。ファイルを読む段、解析する段、集計する段を `Channel` でつないだログ集計のパイプラインで、上流の段が終わると出口の `Channel` を閉じて下流を終わらせる。この例で、取り消した停止コールバックの登録がフレームに残り続ける不具合(`Channel.get()` は待つたびに登録と取り消しを行う)が見つかり、修正した。また、上限のない `Channel` では読む側が速いと入力のほぼ全体が溜まること(100 万行で 112MB)が分かり、容量の上限と、空きを待つ `put(item, ctx)` を加えた(上限 20 で 24MB)。

title: Dogfooding

## NOTICE_001

プロセスでの実行を、引数と戻り値の受け渡し(どちらも pickle 可能)だけに絞って追加することを検討している。この場合 `Shared` はプロセス間では使えないものとする。

title: Possible process execution

kind: General

condition: スレッド版の API が固まった後。

## NOTICE_003

スレッドの強制停止は提供しない。止まらないフレームは stuck frame として報告するところまでが gpframe の責任である。

title: No forced thread termination

kind: General

condition: 方針として継続する。
