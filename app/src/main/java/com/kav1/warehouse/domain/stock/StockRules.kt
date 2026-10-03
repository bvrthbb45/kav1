package com.kav1.warehouse.domain.stock

import com.kav1.warehouse.data.local.ActionType
import com.kav1.warehouse.data.local.ItemStatus

/**
 * Who holds how many units of an item. Same rules as the server
 * (server/app/stock.py), so the tablet shows the right numbers before a sync:
 *
 * - BORROW/ISSUE n: if fewer than n units are free, the missing units are
 *   taken from the other holders (oldest first). With a quantity of 1 this
 *   is "latest action wins".
 * - RETURN n: from that soldier first (borrowed before issued), then others.
 */
object StockRules {

    class Holding(var borrowed: Int, var issued: Int, var since: Long?) {
        val total: Int get() = borrowed + issued
    }

    data class Summary(
        val available: Int,
        val borrowed: Int,
        val issued: Int,
        val status: String,
        /** The soldier who most recently took units, for the item list. */
        val latestHolder: String?,
    )

    /** Applies one action to [holders] (soldier id -> holding), in place. */
    fun apply(
        quantity: Int,
        holders: MutableMap<String, Holding>,
        actionType: String,
        userId: String,
        units: Int,
        timestamp: Long,
    ) {
        val n = units.coerceAtLeast(1)
        if (actionType == ActionType.RETURN) {
            val owed = take(holders.getOrPut(userId) { Holding(0, 0, null) }, n)
            takeFromOthers(holders, userId, owed)
        } else {
            val held = holders.values.sumOf { it.total }
            val short = n - (quantity - held).coerceAtLeast(0)
            if (short > 0) takeFromOthers(holders, userId, short)
            val holding = holders.getOrPut(userId) { Holding(0, 0, null) }
            if (actionType == ActionType.BORROW) holding.borrowed += n else holding.issued += n
            holding.since = timestamp
        }
        holders.values.removeAll { it.total <= 0 }
    }

    fun summarize(quantity: Int, holders: Map<String, Holding>): Summary {
        val borrowed = holders.values.sumOf { it.borrowed }
        val issued = holders.values.sumOf { it.issued }
        val available = (quantity - borrowed - issued).coerceAtLeast(0)
        val status = when {
            holders.isEmpty() || available > 0 -> ItemStatus.AVAILABLE
            borrowed > 0 -> ItemStatus.BORROWED
            else -> ItemStatus.ISSUED
        }
        val latest = holders.maxByOrNull { it.value.since ?: Long.MIN_VALUE }?.key
        return Summary(available, borrowed, issued, status, latest)
    }

    /** Removes up to [n] units (borrowed first); returns how many are still owed. */
    private fun take(holding: Holding, n: Int): Int {
        var left = n
        val b = minOf(holding.borrowed, left)
        holding.borrowed -= b
        left -= b
        val i = minOf(holding.issued, left)
        holding.issued -= i
        return left - i
    }

    private fun takeFromOthers(holders: MutableMap<String, Holding>, skip: String, n: Int) {
        var left = n
        for ((userId, holding) in holders.entries.sortedBy { it.value.since ?: Long.MIN_VALUE }) {
            if (left <= 0) break
            if (userId != skip) left = take(holding, left)
        }
    }
}
