<!--
この文書は `shikumi-devdoc` によって生成された canonical document です。
Canonical source は `devdocs/canonical_sources/specification/__init__.py` です。
直接編集しないでください。

公開文書作成方針

- `devdocs/canonical_documents/` にある日本語 canonical document を公開工程の入力とする。
- 翻訳では意味、構造、情報量を維持し、内容を勝手に追加・削除・要約しない。
- canonical document に `shikumi-devdoc:translation-metadata` が含まれる場合は、その `preserve_spelling` 指定の用語の表記を変更しない。
- コード、Python 識別子、コマンド、ファイルパス、URL は、翻訳上の必要がない限り変更しない。
- このコメントブロックは published document には含めない。
- published document は canonical document から派生する公開成果物として扱い、内容の変更が必要な場合は canonical source または realization context へ戻して canonical document を再生成する。
-->

# Shared

型の固定された共有セル `Shared` の生成、読み書き、アトミックな更新に関する規則。

## SHARED_001

`Shared(typ, value)` の `typ` は、`isinstance()` で検査できる実行時のクラスでなければならず、`NoneType` であってはならない。満たさない場合は `DeclaredTypeError` を送出する。`list[int]` のような型式は拒否される。

title: Declared type

level: MUST

## SHARED_002

`Shared` が保持する値は、常に宣言した型のインスタンスであり、`None` であってはならない。生成時の値、`set()` と `swap()` に渡す値、`apply()` の関数の結果は、すべてこの条件で検査する。満たさない場合は `DeclaredTypeError` を送出し、値は変えない。

title: The value always matches the type

level: MUST

## SHARED_003

型の検査は `isinstance()` による。宣言した型のサブクラスのインスタンスも受け入れる(`Shared(int, 0)` は `True` を受け入れる)。

title: Subclass instances

level: INFORMATIVE

## SHARED_004

`get()` は現在の値を返す。`set(value)` は値を置き換える。`swap(value)` は値を置き換え、置き換える前の値を返す。

title: Reading and replacing

level: MUST

## SHARED_005

`apply(fn)` は、現在の値を `fn` に渡し、その結果で値を置き換え、置き換えた後の値を返す。読み取りから書き込みまでを一つの操作として行い、並行した `apply()`、`set()`、`swap()` の更新を失ってはならない。

title: Atomic update

level: MUST

## SHARED_006

`apply()` の `fn` が例外を送出した場合、その例外をそのまま送出し、値は変えない。

title: Failing update functions

level: MUST

## SHARED_007

`apply()` の `fn` はロックを持ったまま呼ばれるので、短く、副作用がなく、同じ `Shared` を操作しない関数にすべきである。

title: Writing update functions

level: SHOULD

condition: `apply()` に渡す関数を書くとき。

## SHARED_008

複数の値を常に一貫させたい場合は、不変のデータクラスを一つの `Shared` に入れ、`apply()` で丸ごと差し替えるべきである。複数の `Shared` にまたがる不可分な操作は提供しない。

title: Keeping several values consistent

level: SHOULD
