package com.kav1.inventory.ui

import android.app.Application
import androidx.lifecycle.AndroidViewModel
import androidx.lifecycle.SavedStateHandle
import androidx.lifecycle.viewModelScope
import com.kav1.inventory.data.local.ActionType
import com.kav1.inventory.data.local.Item
import com.kav1.inventory.data.local.User
import com.kav1.inventory.inventoryRepository
import com.kav1.inventory.sync.SyncScheduler
import kotlinx.coroutines.flow.MutableSharedFlow
import kotlinx.coroutines.flow.SharedFlow
import kotlinx.coroutines.flow.SharingStarted
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.stateIn
import kotlinx.coroutines.launch

class ItemActionViewModel(
    application: Application,
    savedState: SavedStateHandle,
) : AndroidViewModel(application) {

    private val repository = application.inventoryRepository

    val qrId: String = checkNotNull(savedState.get<String>(ItemActionFragment.ARG_QR_ID))

    val item: StateFlow<Item?> = repository.observeItem(qrId)
        .stateIn(viewModelScope, SharingStarted.WhileSubscribed(5_000), null)

    val users: StateFlow<List<User>> = repository.observeUsers()
        .stateIn(viewModelScope, SharingStarted.WhileSubscribed(5_000), emptyList())

    private val _saved = MutableSharedFlow<Unit>(extraBufferCapacity = 1)
    val saved: SharedFlow<Unit> = _saved

    private var saving = false

    fun save(userId: String, action: ActionType) {
        if (saving) return
        saving = true
        viewModelScope.launch {
            try {
                repository.recordTransaction(qrId, userId, action)
                SyncScheduler.syncNow(getApplication<Application>())
                _saved.emit(Unit)
            } finally {
                saving = false
            }
        }
    }
}
