package com.kav1.warehouse.ui

import android.content.Context
import android.content.Intent
import android.os.Bundle
import android.widget.TextView
import androidx.appcompat.app.AppCompatActivity
import androidx.core.content.ContextCompat
import androidx.lifecycle.Lifecycle
import androidx.lifecycle.lifecycleScope
import androidx.lifecycle.repeatOnLifecycle
import com.kav1.warehouse.R
import com.kav1.warehouse.data.local.ItemStatus
import com.kav1.warehouse.databinding.ActivityUserCardBinding
import kotlinx.coroutines.launch

/** Soldier card: who they are, what they hold now, and their action history. */
class UserCardActivity : AppCompatActivity() {

    private lateinit var binding: ActivityUserCardBinding
    private lateinit var userId: String

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        binding = ActivityUserCardBinding.inflate(layoutInflater)
        setContentView(binding.root)
        setTitle(R.string.card_title)
        supportActionBar?.setDisplayHomeAsUpEnabled(true)
        userId = intent.getStringExtra(EXTRA_USER_ID).orEmpty()
        observe()
    }

    override fun onSupportNavigateUp(): Boolean {
        finish()
        return true
    }

    private fun observe() {
        val repo = app.repository
        lifecycleScope.launch {
            val user = repo.getUser(userId)
            binding.txtName.text = user?.fullName ?: userId
            binding.txtDetails.text = getString(R.string.card_details, userId, user?.unit.orEmpty())
        }
        lifecycleScope.launch {
            repeatOnLifecycle(Lifecycle.State.STARTED) {
                launch {
                    repo.observeHeldBy(userId).collect { items ->
                        val units = items.sumOf { it.borrowed + it.issued }
                        binding.txtHoldingTitle.text = getString(R.string.card_holding_title, units)
                        val list = binding.listHolding
                        list.removeAllViews()
                        if (items.isEmpty()) {
                            list.addView(
                                TextView(this@UserCardActivity).apply {
                                    setText(R.string.card_holding_empty)
                                    setTextColor(ContextCompat.getColor(context, R.color.text_secondary))
                                    textSize = 16f
                                    setPadding(0, 12, 0, 12)
                                },
                            )
                        }
                        items.forEach { item ->
                            val since = item.since?.let { formatDateTime(it) }
                                ?: getString(R.string.card_since_unknown)
                            addListRow(
                                list,
                                item.name ?: item.qrId,
                                heldLabel(item.borrowed, item.issued),
                                statusColor(if (item.borrowed > 0) ItemStatus.BORROWED else ItemStatus.ISSUED),
                                getString(R.string.card_holding_row, categoryLabel(item.category), item.qrId, since),
                            ) { startActivity(ItemActivity.intent(this@UserCardActivity, item.qrId)) }
                        }
                    }
                }
                repo.observeUserHistory(userId).collect { rows ->
                    fillHistory(binding.listHistory, rows, byItem = true) { row ->
                        startActivity(ItemActivity.intent(this@UserCardActivity, row.qrId))
                    }
                }
            }
        }
    }

    companion object {
        private const val EXTRA_USER_ID = "user_id"

        fun intent(context: Context, userId: String): Intent =
            Intent(context, UserCardActivity::class.java).putExtra(EXTRA_USER_ID, userId)
    }
}
