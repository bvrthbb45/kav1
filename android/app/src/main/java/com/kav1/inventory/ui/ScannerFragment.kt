package com.kav1.inventory.ui

import android.Manifest
import android.content.pm.PackageManager
import android.os.Bundle
import android.os.Handler
import android.os.Looper
import android.util.Log
import android.util.Size
import android.view.LayoutInflater
import android.view.View
import android.view.ViewGroup
import androidx.activity.result.contract.ActivityResultContracts
import androidx.camera.core.CameraSelector
import androidx.camera.core.ImageAnalysis
import androidx.camera.core.Preview
import androidx.camera.core.resolutionselector.ResolutionSelector
import androidx.camera.core.resolutionselector.ResolutionStrategy
import androidx.camera.lifecycle.ProcessCameraProvider
import androidx.core.content.ContextCompat
import androidx.core.view.isVisible
import androidx.fragment.app.Fragment
import com.kav1.inventory.databinding.FragmentScannerBinding
import java.util.concurrent.ExecutorService
import java.util.concurrent.Executors
import java.util.concurrent.atomic.AtomicBoolean

class ScannerFragment : Fragment() {

    private var _binding: FragmentScannerBinding? = null
    private val binding get() = _binding!!

    private lateinit var analysisExecutor: ExecutorService
    private val handled = AtomicBoolean(false)
    private val mainHandler = Handler(Looper.getMainLooper())

    private val requestPermission =
        registerForActivityResult(ActivityResultContracts.RequestPermission()) { granted ->
            if (granted) startCamera() else showPermissionDenied()
        }

    override fun onCreateView(inflater: LayoutInflater, container: ViewGroup?, savedInstanceState: Bundle?): View {
        _binding = FragmentScannerBinding.inflate(inflater, container, false)
        return binding.root
    }

    override fun onViewCreated(view: View, savedInstanceState: Bundle?) {
        analysisExecutor = Executors.newSingleThreadExecutor()
        binding.grantPermissionButton.setOnClickListener {
            requestPermission.launch(Manifest.permission.CAMERA)
        }
        if (hasCameraPermission()) startCamera() else requestPermission.launch(Manifest.permission.CAMERA)
    }

    override fun onResume() {
        super.onResume()
        // Re-arm after returning from the item screen.
        handled.set(false)
    }

    private fun hasCameraPermission() =
        ContextCompat.checkSelfPermission(requireContext(), Manifest.permission.CAMERA) ==
            PackageManager.PERMISSION_GRANTED

    private fun showPermissionDenied() {
        binding.permissionGroup.isVisible = true
    }

    private fun startCamera() {
        binding.permissionGroup.isVisible = false
        val providerFuture = ProcessCameraProvider.getInstance(requireContext())
        providerFuture.addListener({
            val binding = _binding ?: return@addListener
            val provider = providerFuture.get()

            val preview = Preview.Builder().build().also {
                it.setSurfaceProvider(binding.previewView.surfaceProvider)
            }
            // A modest resolution is plenty for QR codes and keeps analysis cheap.
            val analysis = ImageAnalysis.Builder()
                .setResolutionSelector(
                    ResolutionSelector.Builder()
                        .setResolutionStrategy(
                            ResolutionStrategy(Size(1280, 720), ResolutionStrategy.FALLBACK_RULE_CLOSEST_LOWER_THEN_HIGHER),
                        )
                        .build(),
                )
                .setBackpressureStrategy(ImageAnalysis.STRATEGY_KEEP_ONLY_LATEST)
                .build()
                .also { it.setAnalyzer(analysisExecutor, QrCodeAnalyzer(::onQrCode)) }

            try {
                provider.unbindAll()
                provider.bindToLifecycle(viewLifecycleOwner, CameraSelector.DEFAULT_BACK_CAMERA, preview, analysis)
            } catch (e: Exception) {
                Log.e(TAG, "Camera binding failed", e)
            }
        }, ContextCompat.getMainExecutor(requireContext()))
    }

    // Called on the analysis thread.
    private fun onQrCode(qrId: String) {
        if (!handled.compareAndSet(false, true)) return
        mainHandler.post {
            if (_binding != null && isResumed) (activity as? MainActivity)?.showItem(qrId) else handled.set(false)
        }
    }

    override fun onDestroyView() {
        super.onDestroyView()
        analysisExecutor.shutdown()
        _binding = null
    }

    private companion object {
        const val TAG = "ScannerFragment"
    }
}
