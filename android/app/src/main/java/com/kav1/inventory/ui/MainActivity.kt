package com.kav1.inventory.ui

import android.os.Bundle
import android.view.Menu
import android.view.MenuItem
import androidx.appcompat.app.AppCompatActivity
import androidx.fragment.app.commit
import androidx.lifecycle.Lifecycle
import androidx.lifecycle.lifecycleScope
import androidx.lifecycle.repeatOnLifecycle
import com.kav1.inventory.R
import com.kav1.inventory.databinding.ActivityMainBinding
import com.kav1.inventory.inventoryRepository
import com.kav1.inventory.sync.SyncScheduler
import kotlinx.coroutines.launch

class MainActivity : AppCompatActivity() {

    private lateinit var binding: ActivityMainBinding

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        binding = ActivityMainBinding.inflate(layoutInflater)
        setContentView(binding.root)
        setSupportActionBar(binding.toolbar)

        if (savedInstanceState == null) {
            supportFragmentManager.commit {
                replace(R.id.fragmentContainer, ScannerFragment())
            }
        }

        lifecycleScope.launch {
            repeatOnLifecycle(Lifecycle.State.STARTED) {
                inventoryRepository.observePendingCount().collect { count ->
                    supportActionBar?.subtitle =
                        if (count == 0) getString(R.string.all_synced)
                        else resources.getQuantityString(R.plurals.pending_count, count, count)
                }
            }
        }
    }

    fun showItem(qrId: String) {
        supportFragmentManager.commit {
            setReorderingAllowed(true)
            replace(R.id.fragmentContainer, ItemActionFragment.newInstance(qrId))
            addToBackStack("item")
        }
    }

    override fun onCreateOptionsMenu(menu: Menu): Boolean {
        menuInflater.inflate(R.menu.main_menu, menu)
        return true
    }

    override fun onOptionsItemSelected(item: MenuItem): Boolean = when (item.itemId) {
        R.id.action_sync -> {
            SyncScheduler.syncNow(this)
            true
        }
        else -> super.onOptionsItemSelected(item)
    }
}
