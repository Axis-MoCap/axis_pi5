import 'package:flutter/cupertino.dart';
import 'package:flutter/material.dart';
import 'package:flutter_svg/flutter_svg.dart';
import '../authentication/login_page.dart';
import '../data/data.dart';

class Onboarding extends StatefulWidget {
  const Onboarding({super.key});

  @override
  State<Onboarding> createState() => _OnboardingState();
}

class _OnboardingState extends State<Onboarding> with TickerProviderStateMixin {
  PageController? _controller;
  int currentIndex = 0;
  double percentage = 0.25;
  late AnimationController _animationController;
  late AnimationController _pulseAnimationController;
  late Animation<double> _fadeAnimation;
  late Animation<Offset> _slideAnimation;
  late Animation<double> _scaleAnimation;
  late Animation<double> _pulseAnimation;

  @override
  void initState() {
    _controller = PageController(initialPage: 0);
    _animationController = AnimationController(
      vsync: this,
      duration: const Duration(milliseconds: 800),
    );
    _pulseAnimationController = AnimationController(
      vsync: this,
      duration: const Duration(milliseconds: 2000),
    )..repeat(reverse: true);

    _fadeAnimation = Tween<double>(begin: 0.0, end: 1.0).animate(
      CurvedAnimation(parent: _animationController, curve: Curves.easeInOut),
    );
    _slideAnimation =
        Tween<Offset>(begin: const Offset(0, 0.3), end: Offset.zero).animate(
      CurvedAnimation(parent: _animationController, curve: Curves.easeOutCubic),
    );
    _scaleAnimation = Tween<double>(begin: 0.85, end: 1.0).animate(
      CurvedAnimation(
        parent: _animationController,
        curve: const Interval(0.2, 1.0, curve: Curves.elasticOut),
      ),
    );
    _pulseAnimation = Tween<double>(begin: 1.0, end: 1.1).animate(
      CurvedAnimation(
        parent: _pulseAnimationController,
        curve: Curves.easeInOut,
      ),
    );

    _animationController.forward();
    super.initState();
  }

  @override
  void dispose() {
    _controller!.dispose();
    _animationController.dispose();
    _pulseAnimationController.dispose();
    super.dispose();
  }

  void _goToNextPage() {
    if (currentIndex == contentsList.length - 1) {
      _goToLogin();
    } else {
      _animationController.reset();
      _controller!.nextPage(
        duration: const Duration(milliseconds: 500),
        curve: Curves.easeInOut,
      );
      _animationController.forward();
    }
  }

  void _goToLogin() {
    // Create heroTag for smooth transition
    final heroTag = 'onboarding-to-login';

    // Animate out current page
    _animationController.reverse().then((_) {
      Navigator.pushReplacement(
        context,
        PageRouteBuilder(
          pageBuilder: (context, animation, secondaryAnimation) =>
              LoginPage(heroTag: heroTag),
          transitionsBuilder: (context, animation, secondaryAnimation, child) {
            // Combine fade and slide for smoother transitions
            var fadeAnimation = Tween<double>(
              begin: 0.0,
              end: 1.0,
            ).animate(
              CurvedAnimation(
                parent: animation,
                curve: const Interval(0.3, 1.0, curve: Curves.easeOut),
              ),
            );

            var slideAnimation = Tween<Offset>(
              begin: const Offset(0.0, 0.2),
              end: Offset.zero,
            ).animate(
              CurvedAnimation(
                parent: animation,
                curve: const Interval(0.3, 1.0, curve: Curves.easeOutCubic),
              ),
            );

            var scaleAnimation = Tween<double>(
              begin: 0.9,
              end: 1.0,
            ).animate(
              CurvedAnimation(
                parent: animation,
                curve: const Interval(0.3, 1.0, curve: Curves.easeOut),
              ),
            );

            return FadeTransition(
              opacity: fadeAnimation,
              child: SlideTransition(
                position: slideAnimation,
                child: ScaleTransition(
                  scale: scaleAnimation,
                  child: child,
                ),
              ),
            );
          },
          transitionDuration: const Duration(milliseconds: 800),
        ),
      );
    });
  }

  @override
  Widget build(BuildContext context) {
    final Size size = MediaQuery.of(context).size;

    return Scaffold(
      body: AnimatedContainer(
        duration: const Duration(milliseconds: 600),
        curve: Curves.easeInOut,
        color: contentsList[currentIndex].backgroundColor,
        child: SafeArea(
          child: Center(
            child: ConstrainedBox(
              constraints: const BoxConstraints(maxWidth: 1000),
              child: Column(
                children: [
                  Expanded(
                    flex: 5,
                    child: PageView.builder(
                      controller: _controller,
                      itemCount: contentsList.length,
                      onPageChanged: (int index) {
                        setState(() {
                          currentIndex = index;
                          percentage = (index + 1) * (1 / contentsList.length);
                          _animationController.reset();
                          _animationController.forward();
                        });
                      },
                      itemBuilder: (context, index) {
                        // Determine layout based on screen width
                        final bool isWide = size.width >= 800;
                        if (isWide) {
                          // Side-by-side layout for large screens
                          return Row(
                            children: [
                              // Text section
                              Expanded(
                                child: Padding(
                                  padding: const EdgeInsets.all(32.0),
                                  child: ScaleTransition(
                                    scale: _scaleAnimation,
                                    child: FadeTransition(
                                      opacity: _fadeAnimation,
                                      child: SlideTransition(
                                        position: _slideAnimation,
                                        child: Column(
                                          mainAxisAlignment:
                                              MainAxisAlignment.center,
                                          crossAxisAlignment:
                                              CrossAxisAlignment.start,
                                          children: [
                                            Text(
                                              contentsList[index].title,
                                              style: const TextStyle(
                                                fontSize: 36,
                                                fontWeight: FontWeight.bold,
                                                color: Colors.white,
                                              ),
                                            ),
                                            const SizedBox(height: 24),
                                            Text(
                                              contentsList[index].discription,
                                              style: const TextStyle(
                                                fontSize: 20,
                                                height: 1.6,
                                                color: Colors.white70,
                                              ),
                                            ),
                                          ],
                                        ),
                                      ),
                                    ),
                                  ),
                                ),
                              ),
                              // Image section
                              Expanded(
                                child: Padding(
                                  padding: const EdgeInsets.all(32.0),
                                  child: ScaleTransition(
                                    scale: _scaleAnimation,
                                    child: FadeTransition(
                                      opacity: _fadeAnimation,
                                      child: SvgPicture.asset(
                                        contentsList[index].image,
                                        fit: BoxFit.contain,
                                      ),
                                    ),
                                  ),
                                ),
                              ),
                            ],
                          );
                        }
                        return Column(
                          crossAxisAlignment:
                              currentIndex == 0 || currentIndex == 3
                                  ? CrossAxisAlignment.start
                                  : CrossAxisAlignment.end,
                          children: [
                            Padding(
                              padding: const EdgeInsets.all(24.0),
                              child: ScaleTransition(
                                scale: _scaleAnimation,
                                child: FadeTransition(
                                  opacity: _fadeAnimation,
                                  child: SlideTransition(
                                    position: _slideAnimation,
                                    child: Column(
                                      crossAxisAlignment:
                                          CrossAxisAlignment.stretch,
                                      children: [
                                        Text(
                                          contentsList[index].title,
                                          style: const TextStyle(
                                            fontFamily: "SF-Pro",
                                            fontStyle: FontStyle.normal,
                                            fontWeight: FontWeight.w700,
                                            fontSize: 32.0,
                                            letterSpacing: 0.5,
                                            color: Colors.white,
                                          ),
                                        ),
                                        const SizedBox(height: 16),
                                        Text(
                                          contentsList[index].discription,
                                          style: const TextStyle(
                                            fontFamily: "SF-Pro",
                                            fontStyle: FontStyle.normal,
                                            fontWeight: FontWeight.w400,
                                            fontSize: 18.0,
                                            height: 1.5,
                                            color: Colors.white,
                                          ),
                                        ),
                                      ],
                                    ),
                                  ),
                                ),
                              ),
                            ),
                            Expanded(
                              child: ScaleTransition(
                                scale: _scaleAnimation,
                                child: FadeTransition(
                                  opacity: _fadeAnimation,
                                  child: Container(
                                    padding: const EdgeInsets.symmetric(
                                        horizontal: 20),
                                    child: SvgPicture.asset(
                                      contentsList[index].image,
                                      fit: BoxFit.contain,
                                    ),
                                  ),
                                ),
                              ),
                            ),
                          ],
                        );
                      },
                    ),
                  ),
                  Container(
                    padding: const EdgeInsets.symmetric(
                        horizontal: 24.0, vertical: 30.0),
                    child: Row(
                      mainAxisAlignment: MainAxisAlignment.spaceBetween,
                      children: [
                        // Pagination indicator
                        Column(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          mainAxisAlignment: MainAxisAlignment.end,
                          children: [
                            Row(
                              children: List.generate(
                                contentsList.length,
                                (index) => buildDot(index, context),
                              ),
                            ),
                            const SizedBox(height: 16),
                            // Skip button
                            CupertinoButton(
                              padding: EdgeInsets.zero,
                              onPressed: _goToLogin,
                              child: const Text(
                                "Skip",
                                style: TextStyle(
                                  color: Colors.white,
                                  fontWeight: FontWeight.w600,
                                  fontSize: 16,
                                ),
                              ),
                            ),
                          ],
                        ),
                        // Next button with progress indicator
                        GestureDetector(
                          onTap: _goToNextPage,
                          child: AnimatedBuilder(
                            animation: _pulseAnimationController,
                            builder: (context, child) => Transform.scale(
                              scale: _pulseAnimation.value,
                              child: Container(
                                height: 70,
                                width: 70,
                                decoration: BoxDecoration(
                                  shape: BoxShape.circle,
                                  boxShadow: [
                                    BoxShadow(
                                      color: Colors.black.withOpacity(0.1),
                                      blurRadius: 10,
                                      offset: const Offset(0, 5),
                                    ),
                                  ],
                                ),
                                child: Stack(
                                  alignment: Alignment.center,
                                  children: [
                                    SizedBox(
                                      height: 70,
                                      width: 70,
                                      child: CircularProgressIndicator(
                                        value: percentage,
                                        backgroundColor: Colors.white38,
                                        valueColor:
                                            const AlwaysStoppedAnimation<Color>(
                                          Colors.white,
                                        ),
                                        strokeWidth: 3,
                                      ),
                                    ),
                                    Container(
                                      height: 60,
                                      width: 60,
                                      decoration: const BoxDecoration(
                                        color: Colors.white,
                                        shape: BoxShape.circle,
                                      ),
                                      child: Icon(
                                        currentIndex == contentsList.length - 1
                                            ? Icons.check
                                            : Icons.arrow_forward_ios_rounded,
                                        color: contentsList[currentIndex]
                                            .backgroundColor,
                                        size: currentIndex ==
                                                contentsList.length - 1
                                            ? 30
                                            : 20,
                                      ),
                                    ),
                                  ],
                                ),
                              ),
                            ),
                          ),
                        ),
                      ],
                    ),
                  ),
                ],
              ),
            ),
          ),
        ),
      ),
    );
  }

  AnimatedContainer buildDot(int index, BuildContext context) {
    return AnimatedContainer(
      duration: const Duration(milliseconds: 500),
      curve: Curves.easeInOutCubic,
      height: 10,
      width: currentIndex == index ? 30 : 10,
      margin: const EdgeInsets.only(right: 8),
      decoration: BoxDecoration(
        borderRadius: BorderRadius.circular(20),
        color: currentIndex == index
            ? Colors.white
            : Colors.white.withOpacity(0.5),
      ),
    );
  }
}
